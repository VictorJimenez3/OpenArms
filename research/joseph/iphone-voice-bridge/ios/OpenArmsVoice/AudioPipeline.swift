import AVFoundation
import Foundation

@MainActor
final class AudioPipeline: NSObject, AVAudioPlayerDelegate {
    private var engine: AVAudioEngine?
    private var player: AVAudioPlayer?
    private var hasTap = false
    var onPlaybackFinished: ((Bool, String?) -> Void)?
    var isCapturing: Bool { engine != nil }
    var isPlaying: Bool { player != nil }

    func activate() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
        try session.setActive(true)
        try session.overrideOutputAudioPort(.speaker)
    }

    func startCapture(into fifo: OutboundFIFO) throws {
        guard engine == nil else { return }
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0,
              let target = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000,
                                         channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: format, to: target) else {
            throw VoiceError.message("This microphone format cannot be converted. Disconnect external audio devices and start again.")
        }
        converter.downmix = true
        let token = fifo.beginCapture()
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            // Conversion happens synchronously in the tap. No captured buffer outlives this callback.
            let capacity = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 16_000 / format.sampleRate) + 64)
            guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else {
                fifo.fail("Could not allocate microphone conversion audio.", captureToken: token)
                return
            }
            var supplied = false
            var error: NSError?
            let status = converter.convert(to: output, error: &error) { _, inputStatus in
                guard !supplied else {
                    inputStatus.pointee = .noDataNow
                    return nil
                }
                supplied = true
                inputStatus.pointee = .haveData
                return buffer
            }
            guard status != .error, error == nil else {
                fifo.fail("Microphone audio conversion failed. Start a new session.", captureToken: token)
                return
            }
            guard output.frameLength > 0, let channel = output.int16ChannelData?[0] else { return }
            let samples = UnsafeBufferPointer(start: channel, count: Int(output.frameLength))
            // The relay accepts at most 200 ms of PCM in one WebSocket message.
            for start in stride(from: 0, to: samples.count, by: 3_200) {
                let count = min(3_200, samples.count - start)
                let frame = UnsafeBufferPointer(start: channel.advanced(by: start), count: count)
                fifo.enqueueAudio(PCMBytes.littleEndian(frame), token: token)
            }
        }
        self.engine = engine
        hasTap = true
        do {
            engine.prepare()
            try engine.start()
        } catch {
            fifo.stopCaptureAndDiscardAudio()
            stopCapture()
            throw error
        }
    }

    func stopCapture() {
        if let engine {
            if hasTap { engine.inputNode.removeTap(onBus: 0) }
            engine.stop()
        }
        hasTap = false
        engine = nil
    }

    func play(_ wav: Data) throws {
        guard player == nil else { throw VoiceError.message("The relay sent overlapping audio replies.") }
        try WaveFile.validate(wav)
        try AVAudioSession.sharedInstance().overrideOutputAudioPort(.speaker)
        let player = try AVAudioPlayer(data: wav, fileTypeHint: AVFileType.wav.rawValue)
        player.delegate = self
        player.numberOfLoops = 0
        self.player = player
        guard player.prepareToPlay(), player.play() else {
            self.player = nil
            throw VoiceError.message("The reply could not play through the speaker. Check audio output and start again.")
        }
    }

    func stopAll() {
        stopCapture()
        player?.delegate = nil
        player?.stop()
        player = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            guard let self, self.player === player else { return }
            self.player = nil
            self.onPlaybackFinished?(flag, flag ? nil : "Reply playback was interrupted. Start a new session.")
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self] in
            guard let self, self.player === player else { return }
            self.player = nil
            self.onPlaybackFinished?(false, "The reply could not be decoded. Start a new session.")
        }
    }
}
