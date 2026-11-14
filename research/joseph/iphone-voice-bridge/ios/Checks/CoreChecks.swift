import Foundation

@main
struct CoreChecks {
    static var checks = 0

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        checks += 1
        guard condition() else { fatalError("FAILED: \(message)") }
    }

    static func rejects(_ message: String, _ operation: () throws -> Void) {
        do { try operation(); fatalError("FAILED: \(message)") }
        catch { checks += 1 }
    }

    static func main() async throws {
        try endpointChecks()
        try protocolChecks()
        queueChecks()
        try waveChecks()
        await wakeupChecks()
        print("PASS: \(checks) protocol, capture gate, PCM, bounded FIFO, concurrency, and WAV checks")
    }

    static func endpointChecks() throws {
        expect(tryResolve(" MacBook.local \n") == "ws://MacBook.local:8765/voice", "hostname expansion")
        expect(tryResolve("mac.local:9000") == "ws://mac.local:9000/voice", "hostname custom port")
        expect(tryResolve("wss://relay.example/voice") == "wss://relay.example/voice", "secure URL preserved")
        expect(tryResolve("ws://127.0.0.1:8765") == "ws://127.0.0.1:8765/voice", "loopback for relay testing")
        expect(tryResolve("ws://[::1]:8765/voice") == "ws://[::1]:8765/voice", "IPv6 URL")
        for bad in ["", "http://mac.local", "ws://", "two words.local", "ws://user:secret@mac.local",
                    "ws://mac.local?token=secret", "ws://mac.local/#fragment", "mac.local:0", "mac.local:65536"] {
            rejects("invalid address: \(bad)") { _ = try RelayEndpoint.resolve(bad) }
        }
    }

    static func tryResolve(_ input: String) -> String? { try? RelayEndpoint.resolve(input).absoluteString }

    static func protocolChecks() throws {
        let event = try JSONDecoder().decode(ServerEvent.self, from: Data("""
        {"type":"session","session_id":"s-1","mode":"mock","logging":true,"raw_audio":false}
        """.utf8))
        expect(event.sessionID == "s-1" && event.logging == true && event.rawAudio == false, "session metadata")
        let escaped = "turn-\"\\\n"
        let control = try JSONSerialization.jsonObject(with: Data(ClientControl.played(escaped).json.utf8)) as! [String: Any]
        expect(control["turn_id"] as? String == escaped, "ack safely escapes turn ID")
        expect(control["type"] as? String == "played", "ack uses protocol event name")
        var gate = CaptureGate()
        expect(!gate.canCapture, "new session cannot capture")
        try gate.receiveState("processing")
        expect(!gate.canCapture, "processing cannot capture")
        try gate.receiveState("listening")
        expect(gate.canCapture, "server listening allows capture")
        gate.setMuted(true)
        expect(!gate.canCapture, "mute immediately closes gate")
        try gate.receiveState("listening")
        expect(!gate.canCapture, "late listening does not override local mute")
        gate.setMuted(false)
        expect(!gate.canCapture, "unmute must wait for another listening event")
        try gate.receiveState("listening")
        expect(gate.canCapture, "fresh listening allows resumed capture")
        gate.beginReply()
        try gate.receiveState("listening")
        expect(!gate.canCapture, "reply blocks premature listening")
        gate.finishReply()
        expect(!gate.canCapture, "playback completion cannot grant listening")
        try gate.receiveState("listening")
        expect(gate.canCapture, "listening after played can capture")
        try gate.receiveState("muted")
        expect(!gate.canCapture, "server mute closes gate")
        rejects("unknown conversation state") { try gate.receiveState("record-anytime") }
        let samples: [Int16] = [0, 1, -1, .min, .max, 0x1234]
        let bytes = samples.withUnsafeBufferPointer(PCMBytes.littleEndian)
        expect(Array(bytes) == [0, 0, 1, 0, 255, 255, 0, 128, 255, 127, 52, 18], "signed PCM little endian bytes")
    }

    static func queueChecks() {
        let fifo = OutboundFIFO(maxFrames: 8, maxBytes: 1024)
        let oldToken = fifo.beginCapture()
        fifo.enqueueAudio(Data([1, 2]), token: oldToken)
        fifo.enqueue(.played("t1"))
        fifo.enqueueAudio(Data([3, 4]), token: oldToken)
        fifo.stopCaptureAndDiscardAudio()
        fifo.enqueue(.mute(true))
        fifo.enqueueAudio(Data([5, 6]), token: oldToken)
        expect(fifo.count == 2, "mute discards queued PCM and rejects late tap callbacks")
        if case let .control(text, _) = fifo.pop() { expect(text.contains("played"), "controls retain order after discard") }
        else { fatalError("expected played control") }
        if case let .control(text, _) = fifo.pop() { expect(text.contains("mute"), "mute follows prior control") }
        else { fatalError("expected mute control") }
        let newToken = fifo.beginCapture()
        fifo.enqueueAudio(Data([1, 2]), token: oldToken)
        expect(fifo.count == 0, "prior capture token cannot feed a restarted tap")
        fifo.enqueueAudio(Data([7, 8]), token: newToken)
        fifo.enqueue(.end)
        if case let .audio(bytes) = fifo.pop() { expect(bytes == Data([7, 8]), "audio and controls share FIFO order") }
        else { fatalError("expected audio") }
        if case let .control(_, ends) = fifo.pop() { expect(ends, "end marked for closing after send") }
        else { fatalError("expected end") }
        expect(fifo.byteCount == 0, "draining releases byte budget")
        fifo.close()
        fifo.enqueue(.ping)
        fifo.enqueueAudio(Data([1, 2]), token: newToken)
        expect(fifo.count == 0, "closed session rejects all frames")

        let overflow = OutboundFIFO(maxFrames: 2, maxBytes: 1024)
        overflow.enqueue(.ping); overflow.enqueue(.ping); overflow.enqueue(.ping)
        expect(overflow.failure != nil && overflow.count == 0, "frame overflow fails closed instead of dropping speech")
        let oversized = OutboundFIFO(maxFrames: 64, maxBytes: 4)
        oversized.enqueueAudio(Data(repeating: 0, count: 6), token: oversized.beginCapture())
        expect(oversized.failure != nil && oversized.byteCount == 0, "byte limit enforced independently")

        let concurrent = OutboundFIFO(maxFrames: 5000, maxBytes: 10000)
        let token = concurrent.beginCapture()
        DispatchQueue.concurrentPerform(iterations: 2000) { index in
            if index == 1000 { concurrent.stopCaptureAndDiscardAudio() }
            concurrent.enqueueAudio(Data([0, 0]), token: token)
        }
        expect(concurrent.count == 0 && concurrent.byteCount == 0, "concurrent mute rejects all old-token producers")
        expect(concurrent.failure == nil, "concurrent race did not overflow")
    }

    static func waveChecks() throws {
        var wave = Array("RIFF".utf8) + le32(40) + Array("WAVEfmt ".utf8) + le32(16)
        wave += le16(1) + le16(1) + le32(16000) + le32(32000) + le16(2) + le16(16)
        wave += Array("data".utf8) + le32(4) + [0, 0, 1, 0]
        try WaveFile.validate(Data(wave))
        expect(wave.count == 48, "valid complete mono WAV accepted")
        for length in 0..<wave.count {
            rejects("truncated WAV at \(length)") { try WaveFile.validate(Data(wave.prefix(length))) }
        }
        var stereo = wave; stereo[22] = 2
        rejects("stereo WAV") { try WaveFile.validate(Data(stereo)) }
        var compressed = wave; compressed[20] = 3
        rejects("float WAV is not integer PCM") { try WaveFile.validate(Data(compressed)) }
        var oversizedChunk = wave; oversizedChunk[40...43] = [255, 255, 255, 127]
        rejects("chunk overrun") { try WaveFile.validate(Data(oversizedChunk)) }
        var empty = wave; empty[40] = 0
        rejects("empty audio data") { try WaveFile.validate(Data(empty)) }
        var invalidRate = wave; invalidRate[24...27] = [0, 0, 0, 0]
        rejects("invalid sample rate") { try WaveFile.validate(Data(invalidRate)) }
        rejects("concatenated WAVs") { try WaveFile.validate(Data(wave + wave)) }
        rejects("size cap") { try WaveFile.validate(Data(repeating: 0, count: WaveFile.maximumBytes + 1)) }
        // The relay may choose another PCM sample rate; microphone rate is a separate requirement.
        var rate44100 = wave
        rate44100[24...27] = ArraySlice(le32(44100))
        rate44100[28...31] = ArraySlice(le32(88200))
        try WaveFile.validate(Data(rate44100))
        expect(true, "reply sample rate need not be 16 kHz")
    }

    static func wakeupChecks() async {
        let fifo = OutboundFIFO()
        fifo.enqueue(.ping)
        fifo.enqueue(.mute(true))
        fifo.enqueue(.played("turn"))
        fifo.close()
        var signals = 0
        for await _ in fifo.wakeups { signals += 1 }
        expect(signals <= 1, "wakeup signals are coalesced instead of becoming another frame queue")
    }

    static func le16(_ value: Int) -> [UInt8] { [UInt8(truncatingIfNeeded: value), UInt8(truncatingIfNeeded: value >> 8)] }
    static func le32(_ value: Int) -> [UInt8] { le16(value) + le16(value >> 16) }
}
