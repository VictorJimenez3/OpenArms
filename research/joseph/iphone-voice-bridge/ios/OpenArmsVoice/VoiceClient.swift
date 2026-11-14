import AVFoundation
import Combine
import Foundation
import UIKit

@MainActor
final class VoiceClient: ObservableObject {
    @Published private(set) var state = "Ready"
    @Published private(set) var detail = "Start a session to hear the first prompt."
    @Published private(set) var errorMessage: String?
    @Published private(set) var active = false
    @Published private(set) var connected = false
    @Published private(set) var ending = false
    @Published private(set) var muted = false
    @Published private(set) var microphoneActive = false
    @Published private(set) var needsMicrophoneSettings = false
    @Published private(set) var sessionID: String?
    @Published private(set) var serverMode: String?
    @Published private(set) var serverLogging: Bool?
    @Published private(set) var serverRawAudio: Bool?
    @Published private(set) var replyText = ""
    @Published private(set) var transcript = ""
    @Published private(set) var endpointInUse: String?

    private let audio = AudioPipeline()
    private var gate = CaptureGate()
    private var connectionID: UUID?
    private var fifo: OutboundFIFO?
    private var socket: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var startupTask: Task<Void, Never>?
    private var readerTask: Task<Void, Never>?
    private var writerTask: Task<Void, Never>?
    private var watchdogTask: Task<Void, Never>?
    private var endingTask: Task<Void, Never>?
    private var pendingTurn: String?
    private var awaitingWAV = false
    private var pingSentAt: ContinuousClock.Instant?
    private var lastPingAt = ContinuousClock.now
    private var connectedAt = ContinuousClock.now
    private var replyDeadline: ContinuousClock.Instant?
    private var observers: [NSObjectProtocol] = []

    init() {
        audio.onPlaybackFinished = { [weak self] success, message in
            self?.playbackFinished(success: success, message: message)
        }
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: AVAudioSession.interruptionNotification,
                                            object: nil, queue: .main) { [weak self] note in
            let value = (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? NSNumber)?.uintValue
            guard value == AVAudioSession.InterruptionType.began.rawValue else { return }
            Task { @MainActor [weak self] in
                guard let self, self.active else { return }
                self.fail("Audio was interrupted by a call or another app. Return here and start a new session.")
            }
        })
        observers.append(center.addObserver(forName: AVAudioSession.routeChangeNotification,
                                            object: nil, queue: .main) { [weak self] note in
            let value = (note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? NSNumber)?.uintValue
            guard let value, let reason = AVAudioSession.RouteChangeReason(rawValue: value),
                  [.newDeviceAvailable, .oldDeviceUnavailable, .noSuitableRouteForCategory,
                   .routeConfigurationChange].contains(reason) else { return }
            Task { @MainActor [weak self] in
                guard let self, self.connected else { return }
                self.fail("The audio route changed. Check the speaker and microphone, then start a new session.")
            }
        })
        observers.append(center.addObserver(forName: .AVAudioEngineConfigurationChange,
                                            object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, self.active, self.audio.isCapturing else { return }
                self.fail("The microphone configuration changed. Start a new session.")
            }
        })
    }

    deinit { observers.forEach(NotificationCenter.default.removeObserver) }

    func start(address: String) {
        guard !active else { return }
        let url: URL
        do { url = try RelayEndpoint.resolve(address) }
        catch { errorMessage = error.localizedDescription; return }

        let id = UUID()
        connectionID = id
        active = true
        ending = false
        errorMessage = nil
        needsMicrophoneSettings = false
        state = "Microphone permission"
        detail = "Allow microphone access to speak with the relay."
        sessionID = nil
        serverMode = nil
        serverLogging = nil
        serverRawAudio = nil
        transcript = ""
        replyText = ""
        endpointInUse = url.absoluteString
        gate = CaptureGate()
        muted = false

        startupTask = Task { [weak self] in
            let allowed = await AVAudioApplication.requestRecordPermission()
            guard let self, self.connectionID == id, !Task.isCancelled else { return }
            guard allowed else {
                self.needsMicrophoneSettings = true
                self.fail("Microphone access is off. Enable it in Settings → Privacy & Security → Microphone → OpenArms Voice, then start again.")
                return
            }
            do {
                try self.audio.activate()
                self.connect(url: url, id: id)
            } catch {
                self.fail("Audio could not start: \(error.localizedDescription)")
            }
        }
    }

    private func connect(url: URL, id: UUID) {
        state = "Connecting"
        detail = "Waiting for the relay. Allow Local Network access if asked."
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 24 * 60 * 60
        configuration.waitsForConnectivity = false
        configuration.urlCredentialStorage = nil
        configuration.httpCookieStorage = nil
        let session = URLSession(configuration: configuration)
        let socket = session.webSocketTask(with: url)
        socket.maximumMessageSize = WaveFile.maximumBytes
        let fifo = OutboundFIFO()
        self.urlSession = session
        self.socket = socket
        self.fifo = fifo
        connectedAt = .now
        lastPingAt = .now
        pingSentAt = nil
        socket.resume()

        writerTask = Task { [weak self] in
            for await _ in fifo.wakeups {
                guard let self, self.connectionID == id, !Task.isCancelled else { return }
                if let failure = fifo.failure { self.fail(failure); return }
                while let frame = fifo.pop() {
                    do {
                        // Exactly one send in flight; controls and audio use the same FIFO.
                        switch frame {
                        case let .audio(data): try await socket.send(.data(data))
                        case let .control(text, endsSession):
                            try await socket.send(.string(text))
                            guard self.connectionID == id else { return }
                            if endsSession { self.finishSession(detail: "Session ended. Start again for a new session."); return }
                        }
                    } catch {
                        guard self.connectionID == id, !Task.isCancelled else { return }
                        self.fail(self.connectionError(error)); return
                    }
                    guard self.connectionID == id, !Task.isCancelled else { return }
                    if let failure = fifo.failure { self.fail(failure); return }
                }
            }
        }
        readerTask = Task { [weak self] in
            do {
                while !Task.isCancelled {
                    let message = try await socket.receive()
                    guard let self, self.connectionID == id else { return }
                    if self.ending { continue }
                    switch message {
                    case let .string(text): try self.receive(text: text)
                    case let .data(data): try self.receive(wav: data)
                    @unknown default: throw VoiceError.message("The relay sent an unsupported WebSocket frame.")
                    }
                }
            } catch {
                guard let self, self.connectionID == id, !Task.isCancelled else { return }
                if self.ending { self.finishSession(detail: "Session ended.") }
                else { self.fail(self.connectionError(error)) }
            }
        }
        watchdogTask = Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
                guard let self, self.connectionID == id else { return }
                let now = ContinuousClock.now
                if !self.connected {
                    if now - self.connectedAt > .seconds(20) {
                        self.fail("The relay did not start a session. Check its hostname, port, Wi-Fi, firewall, and Local Network permission in Settings.")
                        return
                    }
                    continue
                }
                if let deadline = self.replyDeadline, now > deadline {
                    self.fail("The relay did not finish sending its reply audio. Start a new session."); return
                }
                if let sent = self.pingSentAt {
                    if now - sent > .seconds(15) {
                        self.fail("The relay stopped responding. Check Wi-Fi and the relay, then start a new session."); return
                    }
                } else if now - self.lastPingAt > .seconds(10) {
                    // Deadline includes time queued behind audio, so a stuck send also times out.
                    self.pingSentAt = now
                    self.lastPingAt = now
                    fifo.enqueue(.ping)
                }
            }
        }
    }

    private func receive(text: String) throws {
        guard text.utf8.count <= 64 * 1024 else { throw VoiceError.message("The relay sent an oversized event.") }
        let event = try JSONDecoder().decode(ServerEvent.self, from: Data(text.utf8))
        if event.type == "error" {
            guard let message = event.message, let fatal = event.fatal else {
                throw VoiceError.message("The relay sent an incomplete error event.")
            }
            let message = String(message.prefix(2000))
            stopCapture()
            try gate.receiveState("processing")
            if fatal { fail(message) }
            else { errorMessage = message; state = "Waiting for relay"; detail = "The relay reported an error and will send the next state." }
            return
        }
        if event.type == "session" {
            guard !connected, let session = event.sessionID, !session.isEmpty,
                  let mode = event.mode, let logging = event.logging, let raw = event.rawAudio else {
                throw VoiceError.message("The relay sent invalid session information.")
            }
            sessionID = session
            serverMode = mode
            serverLogging = logging
            serverRawAudio = raw
            connected = true
            state = "Preparing reply"
            detail = "Connected. Waiting for the opening prompt."
            return
        }
        guard connected else { throw VoiceError.message("The relay sent an event before starting a session.") }
        switch event.type {
        case "pong": pingSentAt = nil
        case "state":
            guard let value = event.state else { throw VoiceError.message("The relay omitted its state.") }
            try gate.receiveState(value)
            if pendingTurn != nil {
                // Never capture while a reply is pending, even if the server sends listening early.
                stopCapture()
                return
            }
            if gate.canCapture {
                guard let fifo else { return }
                try audio.startCapture(into: fifo)
                microphoneActive = true
                state = "Listening"
                detail = "Speak now. Pause when you have finished your thought."
            } else {
                stopCapture()
                state = muted || value == "muted" ? "Muted" : "Preparing reply"
                detail = muted ? "Your microphone is off. Replies can still play." : "Your microphone is off while the relay prepares a reply."
            }
        case "reply":
            guard pendingTurn == nil, let turn = event.turnID, !turn.isEmpty, let text = event.text else {
                throw VoiceError.message("The relay sent an invalid or overlapping reply.")
            }
            gate.beginReply()
            stopCapture()
            pendingTurn = turn
            awaitingWAV = true
            replyDeadline = .now.advanced(by: .seconds(30))
            replyText = String(text.prefix(6000))
            state = "Receiving reply"
            detail = "Your microphone is off. The reply will play on the speaker."
        case "transcript":
            guard event.role == "student", let text = event.text else {
                throw VoiceError.message("The relay sent an invalid transcript.")
            }
            transcript = String(text.prefix(6000))
        default: throw VoiceError.message("The relay sent an unsupported event: \(event.type.prefix(60)).")
        }
    }

    private func receive(wav: Data) throws {
        guard connected, pendingTurn != nil, awaitingWAV else {
            throw VoiceError.message("The relay sent audio without exactly one pending reply.")
        }
        awaitingWAV = false
        replyDeadline = nil
        stopCapture()
        try audio.play(wav)
        state = "Speaking"
        detail = muted ? "Reply playing. Your microphone remains muted." : "Reply playing on the speaker. Your microphone is off."
    }

    private func playbackFinished(success: Bool, message: String?) {
        guard active, !ending, let turn = pendingTurn else { return }
        guard success else { fail(message ?? "Reply playback failed. Start a new session."); return }
        pendingTurn = nil
        gate.finishReply()
        fifo?.enqueue(.played(turn))
        state = muted ? "Muted" : "Waiting for relay"
        detail = muted ? "Your microphone is off. Unmute when you are ready." : "Reply finished. Waiting for the relay to allow listening."
    }

    func toggleMute() {
        guard connected, !ending else { return }
        muted.toggle()
        gate.setMuted(muted)
        // Close the thread-safe gate before removing the tap; racing old callbacks are rejected.
        stopCapture()
        fifo?.enqueue(.mute(muted))
        if audio.isPlaying {
            detail = muted ? "Reply playing. Your microphone remains muted." : "Reply playing. Waiting for the relay before listening."
        } else {
            state = muted ? "Muted" : "Waiting for relay"
            detail = muted ? "Your microphone is off. Replies can still play." : "Unmute requested. Waiting for the relay to allow listening."
        }
    }

    func end() {
        guard active, !ending else { return }
        ending = true
        stopCapture()
        audio.stopAll()
        state = "Ending session"
        detail = "Closing the connection."
        watchdogTask?.cancel()
        guard let fifo, let id = connectionID, connected else {
            finishSession(detail: "Session ended.")
            return
        }
        fifo.enqueue(.end)
        // Do not wait indefinitely for a blocked write. Closing the socket also ends the session.
        endingTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(1)) } catch { return }
            guard let self, self.connectionID == id else { return }
            self.finishSession(detail: "Session ended.")
        }
    }

    func enteredBackground() {
        guard active else { return }
        finishSession(detail: "The session ended when the app left the foreground. Start again for a new session.")
    }

    private func stopCapture() {
        fifo?.stopCaptureAndDiscardAudio()
        audio.stopCapture()
        microphoneActive = false
    }

    private func cleanup() {
        connectionID = nil // Invalidate all callbacks before canceling their resources.
        stopCapture()
        audio.stopAll()
        startupTask?.cancel(); startupTask = nil
        readerTask?.cancel(); readerTask = nil
        writerTask?.cancel(); writerTask = nil
        watchdogTask?.cancel(); watchdogTask = nil
        endingTask?.cancel(); endingTask = nil
        fifo?.close(); fifo = nil
        socket?.cancel(with: .normalClosure, reason: nil); socket = nil
        urlSession?.invalidateAndCancel(); urlSession = nil
        pendingTurn = nil
        awaitingWAV = false
        replyDeadline = nil
        pingSentAt = nil
        gate = CaptureGate()
        muted = false
        active = false
        connected = false
        ending = false
    }

    private func finishSession(detail: String) {
        cleanup()
        state = "Ready"
        self.detail = detail
    }

    private func fail(_ message: String) {
        cleanup()
        state = "Session stopped"
        detail = "Resolve the issue below, then start a new session."
        errorMessage = message
        UIAccessibility.post(notification: .announcement, argument: "Session stopped. \(message)")
    }

    private func connectionError(_ error: Error) -> String {
        if let error = error as? VoiceError { return error.localizedDescription }
        if error is DecodingError { return "The relay sent an event the app could not read. Check that client and relay use the same protocol." }
        let code = (error as NSError).code
        if (error as NSError).domain == NSURLErrorDomain {
            switch code {
            case NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed:
                return "The relay hostname could not be found. Use the Mac's .local hostname and connect both devices to the same Wi-Fi."
            case NSURLErrorAppTransportSecurityRequiresSecureConnection:
                return "iOS blocked this address. Use the Mac's .local hostname for local ws://, or a trusted wss:// endpoint."
            case NSURLErrorSecureConnectionFailed, NSURLErrorServerCertificateUntrusted:
                return "The relay's secure connection could not be verified. Use a trusted certificate or the local .local ws:// relay."
            default: break
            }
        }
        return "Connection lost or unavailable. Check the relay, Wi-Fi, firewall, and Local Network permission in Settings. \(error.localizedDescription)"
    }
}
