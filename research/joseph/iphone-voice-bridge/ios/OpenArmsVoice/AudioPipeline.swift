import AVFoundation
import Foundation

/// Owned only by VoiceClient. All scheduling and lifecycle changes run on the main actor.
@MainActor
final class AudioPipeline {
    private var engine: AVAudioEngine?
    private var player: AVAudioPlayerNode?
    private var hasTap = false
    private var ledger = PlaybackLedger()
    private var bufferedFrames = 0
    private var playbackEpoch = UUID()
    private let outputFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24_000, channels: 1, interleaved: false)!
    var onPlaybackFinished: ((String) -> Void)?
    var onPlaybackChanged: ((Bool) -> Void)?
    var isCapturing: Bool { hasTap }
    var activeReply: String? { ledger.replyID }
    var needsRestart: Bool { engine?.isRunning == false }

    func ownsEngine(_ configurationSource: ObjectIdentifier) -> Bool {
        engine.map(ObjectIdentifier.init) == configurationSource
    }

    func activate() throws {
        if let engine {
            guard !engine.isRunning else { return }
            // A stopped graph cannot certify queued playback or reuse the old input tap.
            guard bufferedFrames == 0, !hasTap else {
                throw VoiceError.message("The audio route changed while voice was active.")
            }
            player?.stop()
            engine.prepare()
            try engine.start()
            return
        }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setActive(true)
        let engine = AVAudioEngine()
        // Voice processing provides acoustic echo cancellation for simultaneous mic/speaker use.
        try engine.inputNode.setVoiceProcessingEnabled(true)
        let player = AVAudioPlayerNode()
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: outputFormat)
        engine.prepare()
        try engine.start()
        self.engine = engine; self.player = player
    }

    func startCapture(into fifo: OutboundFIFO, generation: Int) throws {
        try activate()
        guard !hasTap, let engine else { return }
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0,
              let target = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: format, to: target) else {
            throw VoiceError.message("This microphone is unavailable. Try another audio route or use text.")
        }
        converter.downmix = true
        let token = fifo.beginCapture(epoch: generation)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            let capacity = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 16_000 / format.sampleRate) + 64)
            guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else {
                fifo.fail("Microphone conversion could not allocate audio.", token: token); return
            }
            var supplied = false
            var error: NSError?
            let status = converter.convert(to: output, error: &error) { _, inputStatus in
                if supplied { inputStatus.pointee = .noDataNow; return nil }
                supplied = true; inputStatus.pointee = .haveData; return buffer
            }
            guard status != .error, error == nil else { fifo.fail("Microphone conversion failed.", token: token); return }
            guard let channel = output.int16ChannelData?[0], output.frameLength > 0 else { return }
            for start in stride(from: 0, to: Int(output.frameLength), by: 1600) {
                let samples = UnsafeBufferPointer(start: channel.advanced(by: start), count: min(1600, Int(output.frameLength) - start))
                fifo.enqueueAudio(PCMBytes.littleEndian(samples), token: token)
            }
        }
        hasTap = true
    }

    func stopCapture() {
        if hasTap { engine?.inputNode.removeTap(onBus: 0) }
        hasTap = false
    }

    func beginReply(_ id: String) throws {
        interruptPlayback()
        try activate()
        ledger.begin(id)
    }

    func append(_ bytes: Data, replyID: String) throws {
        guard ledger.replyID == replyID, let player else { return } // Stale reply audio is never scheduled.
        try activate()
        let samples = try PCMBytes.floats(bytes)
        guard bufferedFrames + samples.count <= 24_000 * 12 else {
            throw VoiceError.message("Voice playback fell behind. The reply was interrupted; use text or try voice again.")
        }
        guard let buffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: AVAudioFrameCount(samples.count)),
              let channel = buffer.floatChannelData?[0] else { throw VoiceError.message("Could not buffer streamed playback.") }
        guard let token = ledger.schedule(replyID) else { return }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { source in channel.update(from: source.baseAddress!, count: samples.count) }
        bufferedFrames += samples.count
        let epoch = playbackEpoch
        let count = samples.count
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, self.playbackEpoch == epoch, self.engine?.isRunning == true else { return }
                self.bufferedFrames = max(0, self.bufferedFrames - count)
                if let done = self.ledger.played(token, reply: replyID) { self.completed(done) }
            }
        }
        if !player.isPlaying { player.play() }
        onPlaybackChanged?(true)
    }

    func endReply(_ id: String) {
        guard engine?.isRunning == true else { return }
        if let done = ledger.finish(id) { completed(done) }
    }

    private func completed(_ id: String) {
        onPlaybackChanged?(false)
        onPlaybackFinished?(id)
    }

    @discardableResult
    func interruptPlayback() -> String? {
        let id = ledger.replyID
        playbackEpoch = UUID() // Invalidate stop-triggered completion callbacks before touching the node.
        ledger.invalidate(); bufferedFrames = 0
        player?.stop()
        onPlaybackChanged?(false)
        return id
    }

    func stopAll() {
        stopCapture()
        interruptPlayback()
        engine?.stop(); engine = nil; player = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
    }
}
