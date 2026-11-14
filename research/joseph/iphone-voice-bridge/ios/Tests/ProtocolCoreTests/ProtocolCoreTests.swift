import Foundation
import XCTest
@testable import VoiceProtocol

final class ProtocolCoreTests: XCTestCase {
    func testEndpointDefaultsAndValidation() throws {
        XCTAssertEqual(try RelayEndpoint.resolve(" MAC-HOST.local ").absoluteString, "ws://MAC-HOST.local:8765/voice")
        XCTAssertEqual(try RelayEndpoint.resolve("wss://example.org/voice").absoluteString, "wss://example.org/voice")
        for invalid in ["", "http://host", "ws://user:secret@host/voice", "ws://host:0", "ws://host/voice?secret=x", "ws://host/#fragment", "bad host"] {
            XCTAssertThrowsError(try RelayEndpoint.resolve(invalid), invalid)
        }
    }

    func testCaptureRequiresServerListeningAndLocalConsent() throws {
        var gate = CaptureGate()
        XCTAssertFalse(gate.canCapture)
        try gate.receiveState("listening")
        XCTAssertTrue(gate.canCapture)
        gate.setMuted(true)
        try gate.receiveState("listening") // Delayed state cannot override local mute.
        XCTAssertFalse(gate.canCapture)
        gate.setMuted(false)
        XCTAssertFalse(gate.canCapture)
        try gate.receiveState("listening")
        gate.beginReply()
        try gate.receiveState("listening") // Reply still owns the speaker.
        XCTAssertFalse(gate.canCapture)
        gate.finishReply()
        XCTAssertFalse(gate.canCapture)
        try gate.receiveState("listening")
        XCTAssertTrue(gate.canCapture)
        try gate.receiveState("processing")
        XCTAssertFalse(gate.canCapture)
        XCTAssertThrowsError(try gate.receiveState("unexpected"))
    }

    func testMuteDiscardsAudioPreservesControlsAndRejectsStaleCallbacks() throws {
        let fifo = OutboundFIFO()
        let old = fifo.beginCapture()
        fifo.enqueueAudio(Data([1, 2]), token: old)
        fifo.enqueue(.played("t-1"))
        fifo.enqueueAudio(Data([3, 4]), token: old)
        fifo.stopCaptureAndDiscardAudio()
        fifo.enqueue(.mute(true))
        fifo.enqueueAudio(Data([5, 6]), token: old)
        fifo.fail("stale conversion", captureToken: old)
        XCTAssertNil(fifo.failure)
        XCTAssertEqual(try control(fifo.pop())["type"] as? String, "played")
        XCTAssertEqual(try control(fifo.pop())["muted"] as? Bool, true)
        XCTAssertNil(fifo.pop())
        let fresh = fifo.beginCapture()
        fifo.enqueueAudio(Data([7, 8]), token: old)
        fifo.enqueueAudio(Data([9, 10]), token: fresh)
        guard case let .audio(bytes)? = fifo.pop() else { return XCTFail("Missing current audio") }
        XCTAssertEqual(bytes, Data([9, 10]))
        fifo.close()
        fifo.enqueue(.end)
        fifo.enqueueAudio(Data([11, 12]), token: fresh)
        XCTAssertNil(fifo.pop())
        XCTAssertEqual(fifo.byteCount, 0)
    }

    func testConcurrentMuteInvalidatesProducer() {
        let fifo = OutboundFIFO(maxFrames: 20_000, maxBytes: 100_000)
        let token = fifo.beginCapture()
        DispatchQueue.concurrentPerform(iterations: 2000) { index in
            if index == 500 { fifo.stopCaptureAndDiscardAudio() }
            fifo.enqueueAudio(Data([0, 0]), token: token)
        }
        XCTAssertEqual(fifo.count, 0)
        XCTAssertNil(fifo.failure)
    }

    func testQueueOverflowFailsClosedRatherThanDroppingArbitraryAudio() {
        let fifo = OutboundFIFO(maxFrames: 1, maxBytes: 4)
        let token = fifo.beginCapture()
        fifo.enqueueAudio(Data([0, 0]), token: token)
        fifo.enqueueAudio(Data([0, 0]), token: token)
        XCTAssertNotNil(fifo.failure)
        XCTAssertEqual(fifo.count, 0)
        XCTAssertNil(fifo.pop())
    }

    func testControlOrderAndEscapedTurnIdentifiers() throws {
        let fifo = OutboundFIFO()
        let token = fifo.beginCapture()
        fifo.enqueue(.ping)
        fifo.enqueueAudio(Data([0, 0]), token: token)
        fifo.enqueue(.played("t-\"\\\n"))
        fifo.enqueue(.end)
        XCTAssertEqual(try control(fifo.pop())["type"] as? String, "ping")
        guard case .audio? = fifo.pop() else { return XCTFail("Audio order changed") }
        XCTAssertEqual(try control(fifo.pop())["turn_id"] as? String, "t-\"\\\n")
        guard case let .control(_, ends)? = fifo.pop() else { return XCTFail("Missing end") }
        XCTAssertTrue(ends)
    }

    func testSignedLittleEndianPCM() {
        let samples: [Int16] = [0, 1, -1, .min, .max, 0x1234]
        XCTAssertEqual(samples.withUnsafeBufferPointer(PCMBytes.littleEndian),
                       Data([0, 0, 1, 0, 255, 255, 0, 128, 255, 127, 0x34, 0x12]))
    }

    func testCompleteMonoPCMAndMalformedWAVs() throws {
        let valid = wave()
        try WaveFile.validate(valid)
        XCTAssertThrowsError(try WaveFile.validate(valid.dropLast()))
        var stereo = valid; stereo[22] = 2
        XCTAssertThrowsError(try WaveFile.validate(stereo))
        var compressed = valid; compressed[20] = 3
        XCTAssertThrowsError(try WaveFile.validate(compressed))
        var badRate = valid; badRate[28] = 0
        XCTAssertThrowsError(try WaveFile.validate(badRate))
        var oversizedChunk = valid; oversizedChunk[43] = 255
        XCTAssertThrowsError(try WaveFile.validate(oversizedChunk))
        var badAlignment = valid; badAlignment[32] = 1
        XCTAssertThrowsError(try WaveFile.validate(badAlignment))
        XCTAssertThrowsError(try WaveFile.validate(Data()))
    }

    private func control(_ frame: OutboundFIFO.Frame?) throws -> [String: Any] {
        guard case let .control(text, _)? = frame else {
            XCTFail("Expected control frame")
            return [:]
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any])
    }

    private func wave() -> Data {
        var result = Data("RIFF".utf8)
        func u16(_ value: UInt16) { result.append(UInt8(truncatingIfNeeded: value)); result.append(UInt8(truncatingIfNeeded: value >> 8)) }
        func u32(_ value: UInt32) { u16(UInt16(truncatingIfNeeded: value)); u16(UInt16(truncatingIfNeeded: value >> 16)) }
        u32(38); result.append(Data("WAVEfmt ".utf8)); u32(16)
        u16(1); u16(1); u32(16_000); u32(32_000); u16(2); u16(16)
        result.append(Data("data".utf8)); u32(2); u16(0)
        return result
    }
}
