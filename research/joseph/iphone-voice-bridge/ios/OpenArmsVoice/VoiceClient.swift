import AVFoundation
import Combine
import Foundation
import Security
import UIKit

private final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil) // A bearer credential must never follow a redirect to another origin.
    }
}

private enum SessionVault {
    static let service = "org.openarms.ph.session"
    static func read(origin: String) throws -> SessionCredential? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
            kSecAttrAccount as String: origin, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        if status == errSecInteractionNotAllowed {
            throw VoiceError.message("Unlock this iPhone to restore your private lab session.")
        }
        guard status == errSecSuccess, let data = item as? Data else {
            throw VoiceError.message("Private session storage is unavailable (\(status)). Reinstall a signed app build before connecting.")
        }
        return try JSONDecoder().decode(SessionCredential.self, from: data)
    }
    static func save(_ credential: SessionCredential) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
            kSecAttrAccount as String: credential.origin]
        let attributes: [String: Any] = [kSecValueData as String: try JSONEncoder().encode(credential),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var item = query; attributes.forEach { item[$0.key] = $0.value }
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw VoiceError.message("Could not save the private session on this iPhone.") }
        } else if status != errSecSuccess { throw VoiceError.message("Could not update the private session on this iPhone.") }
    }
    static func remove(origin: String) {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: origin] as CFDictionary)
    }
}

private struct HTTPFailure: Error { let code: Int }
private struct CaptureQueueFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

private final class AudioNotificationObservers {
    var tokens: [NSObjectProtocol] = []
    deinit { for token in tokens { NotificationCenter.default.removeObserver(token) } }
}

@MainActor
final class VoiceClient: ObservableObject {
    @Published private(set) var snapshot: LabSnapshot?
    @Published private(set) var messages: [LabMessage] = []
    @Published private(set) var connected = false
    @Published private(set) var connecting = false
    @Published private(set) var voiceWanted = false
    @Published private(set) var microphoneActive = false
    @Published private(set) var speakerActive = false
    @Published private(set) var muted = false
    @Published private(set) var voiceStatus = "off"
    @Published private(set) var connectionStatus = "Connect your lab"
    @Published private(set) var notice: String?
    @Published private(set) var needsMicrophoneSettings = false
    @Published private(set) var busy = false
    @Published private(set) var acknowledgedProposal: String?

    private let audio = AudioPipeline()
    private let redirectDelegate = NoRedirects()
    private lazy var http: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 15; config.timeoutIntervalForResource = 20
        config.urlCache = nil; config.httpCookieStorage = nil
        return URLSession(configuration: config, delegate: redirectDelegate, delegateQueue: nil)
    }()
    private var origin: URL?
    private var credential: SessionCredential?
    private var pairingToken = ""
    private var socket: URLSessionWebSocketTask?
    private var fifo: OutboundFIFO?
    private var connectionID: UUID?
    private var snapshotStore = SnapshotStore()
    private var transcripts = TranscriptStore()
    private var heartbeat = Heartbeat(now: 0)
    private var openedAt: TimeInterval = 0
    private var retryCount = 0
    private var wantsConnection = false
    private var foreground = true
    private var audioSuspended = false
    private var providerReady = false
    private var visibleProposal: String?
    private var presentingProposal: String?
    private var startupTask: Task<Void, Never>?
    private var readerTask: Task<Void, Never>?
    private var writerTask: Task<Void, Never>?
    private var heartbeatTask: Task<Void, Never>?
    private var retryTask: Task<Void, Never>?
    private var actionTask: Task<Void, Never>?
    private var actionID: UUID?
    private var presentationTask: Task<Void, Never>?
    private var voiceTask: Task<Void, Never>?
    private var audioRecoveryTask: Task<Void, Never>?
    private let observers = AudioNotificationObservers()

    var canAct: Bool { connected && !busy && foreground }
    var canConfirm: Bool {
        guard canAct, let p = snapshot?.pending else { return false }
        return isCurrent(p) && p.presented && acknowledgedProposal == p.id && visibleProposal == p.id
    }
    init() {
        audio.onPlaybackChanged = { [weak self] playing in self?.speakerActive = playing }
        audio.onPlaybackFinished = { [weak self] id in
            guard let self, self.connected, self.foreground else { return }
            self.fifo?.enqueue(.reply("played", id: id))
            // The server binds played to reply_start's exact proposal/version. Text presentation
            // is acknowledged separately only after the proposal card has appeared.
        }
        let center = NotificationCenter.default
        observers.tokens.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] note in
            let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            let options = note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
            Task { @MainActor [weak self] in self?.interruption(raw: raw, options: options) }
        })
        observers.tokens.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] note in
            let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt ?? 0
            Task { @MainActor [weak self] in self?.routeChanged(raw) }
        })
        observers.tokens.append(center.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in self?.recoverAudio() }
        })
    }

    func connect(address: String, pairingToken: String = "", allowLocalDebug: Bool = false) {
        do {
            let endpoint = try AppEndpoint.resolve(address, allowLocalDebug: allowLocalDebug)
            closeTransport()
            if origin != endpoint { snapshotStore = SnapshotStore(); snapshot = nil; transcripts.restore([]); messages = []; credential = nil }
            origin = endpoint; self.pairingToken = pairingToken
            wantsConnection = true; retryCount = 0; notice = nil
            startConnection()
        } catch { notice = error.localizedDescription }
    }

    private func startConnection() {
        guard foreground, wantsConnection, let origin else { return }
        connecting = true; connectionStatus = retryCount > 0 ? "Reconnecting to your lab…" : "Opening your lab…"
        let attempt = UUID(); connectionID = attempt
        startupTask = Task { [weak self] in
            guard let self else { return }
            do {
                if self.credential == nil { self.credential = try SessionVault.read(origin: origin.absoluteString) }
                var restored: LabSnapshot?
                if let saved = self.credential {
                    do { restored = try await self.request(url: AppEndpoint.sessionURL(origin, id: saved.sessionID), method: "GET", token: saved.accessToken) }
                    catch let e as HTTPFailure where e.code == 401 || e.code == 403 || e.code == 404 {
                        try Task.checkCancellation()
                        guard self.connectionID == attempt else { return }
                        SessionVault.remove(origin: origin.absoluteString); self.credential = nil
                    }
                }
                if restored == nil {
                    let created = try await self.request(url: origin.appendingPathComponent("api/sessions"), method: "POST", token: self.pairingToken.isEmpty ? nil : self.pairingToken, fields: [:])
                    try Task.checkCancellation()
                    guard self.connectionID == attempt else { return }
                    guard let token = created.accessToken, !token.isEmpty else { throw VoiceError.message("The server did not issue a session credential.") }
                    let saved = SessionCredential(origin: origin.absoluteString, sessionID: created.sessionID, accessToken: token)
                    try SessionVault.save(saved); self.credential = saved; self.snapshotStore = SnapshotStore(); restored = created
                    self.pairingToken = ""
                }
                try Task.checkCancellation()
                guard self.connectionID == attempt, let saved = self.credential, let restored else { return }
                guard restored.sessionID == saved.sessionID else { throw VoiceError.message("The restored session did not match this iPhone’s credential.") }
                try self.apply(restored, restoring: true)
                let ws = self.http.webSocketTask(with: try AppEndpoint.liveURL(origin, id: saved.sessionID))
                ws.maximumMessageSize = 2 * 1024 * 1024
                self.socket = ws; self.fifo = OutboundFIFO()
                self.heartbeat = Heartbeat(now: ProcessInfo.processInfo.systemUptime)
                self.openedAt = ProcessInfo.processInfo.systemUptime
                ws.resume()
                self.fifo?.enqueue(.hello(id: attempt, token: saved.accessToken))
                self.read(from: ws, attempt: attempt)
                self.write(to: ws, attempt: attempt)
                self.watch(attempt: attempt)
            } catch is CancellationError { }
            catch { if self.connectionID == attempt { self.connectionFailed(error) } }
        }
    }

    private func request(url: URL, method: String, token: String?, fields: [String: JSONValue]? = nil) async throws -> LabSnapshot {
        var request = URLRequest(url: url)
        request.httpMethod = method; request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let fields { request.httpBody = try JSONEncoder().encode(fields); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await http.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw VoiceError.message("The lab returned an invalid response.") }
        guard (200...299).contains(response.statusCode) else { throw HTTPFailure(code: response.statusCode) }
        guard data.count <= 8 * 1024 * 1024 else { throw VoiceError.message("Lab history is too large to restore safely.") }
        return try LabWire.snapshot(data)
    }

    struct EvidenceScope: Hashable {
        let connection: UUID
        let sessionID: String
        let generation: Int
    }

    var evidenceScope: EvidenceScope? {
        guard connected, foreground, let connectionID, let snapshot,
              snapshot.generation == snapshotStore.audioGeneration,
              snapshot.sessionID == credential?.sessionID else { return nil }
        return EvidenceScope(connection: connectionID, sessionID: snapshot.sessionID, generation: snapshot.generation)
    }

    func loadEvidenceImage(id: String, path: String, scope: EvidenceScope) async throws -> UIImage {
        guard scope == evidenceScope, let origin, let credential else {
            throw CancellationError()
        }
        try Task.checkCancellation()
        let request = try AppEndpoint.evidenceRequest(origin, credential: credential, evidenceID: id, artifactPath: path)
        let (data, response) = try await http.data(for: request)
        try Task.checkCancellation()
        guard scope == evidenceScope else { throw CancellationError() }
        guard let response = response as? HTTPURLResponse,
              response.statusCode == 200, response.mimeType == "image/png",
              data.count <= 8 * 1024 * 1024, let image = UIImage(data: data) else {
            throw VoiceError.message("The scene image is unavailable.")
        }
        return image
    }

    private func read(from ws: URLSessionWebSocketTask, attempt: UUID) {
        readerTask = Task { [weak self] in
            do {
                while !Task.isCancelled {
                    let message = try await ws.receive()
                    guard let self, self.connectionID == attempt else { return }
                    let data: Data
                    switch message { case let .string(text): data = Data(text.utf8); case .data: throw VoiceError.message("The lab sent unsupported binary audio."); @unknown default: continue }
                    try self.receive(LabWire.event(data), attempt: attempt)
                }
            } catch is CancellationError { }
            catch { guard let self, self.connectionID == attempt else { return }; self.connectionFailed(error) }
        }
    }

    private func write(to ws: URLSessionWebSocketTask, attempt: UUID) {
        guard let fifo else { return }
        writerTask = Task { [weak self] in
            do {
                for await _ in fifo.wakeups {
                    guard let self, self.connectionID == attempt else { return }
                    if let problem = fifo.failure { throw CaptureQueueFailure(message: problem) }
                    while let frame = fifo.pop() {
                        // One send may already be in flight at mute. No buffered audio survives.
                        try Task.checkCancellation()
                        try await ws.send(.string(frame.json))
                    }
                }
            } catch is CancellationError { }
            catch { guard let self, self.connectionID == attempt else { return }; self.connectionFailed(error) }
        }
    }

    private func watch(attempt: UUID) {
        heartbeatTask = Task { [weak self] in
            var ticks = 0
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
                guard let self, self.connectionID == attempt else { return }
                let now = ProcessInfo.processInfo.systemUptime
                if self.heartbeat.expired(now: now) { self.connectionFailed(URLError(.timedOut)); return }
                ticks += 1
                if ticks % 5 == 0 && self.connected {
                    self.fifo?.enqueue(ClientFrame(type: "ping", fields: ["seq": .number(Double(self.heartbeat.ping()))]))
                }
                if self.connected && now - self.openedAt >= 30 { self.retryCount = 0 }
            }
        }
    }

    private func receive(_ event: ServerEvent, attempt: UUID) throws {
        if event.type == "hello" {
            guard !connected, event.protocolVersion == 1, event.connectionID == attempt.uuidString, let epoch = event.generation,
                  snapshotStore.acceptHello(generation: epoch) else { throw VoiceError.message("The lab connection contract did not match this client.") }
            connected = true; connecting = false; connectionStatus = "Your lab is connected"
            if voiceWanted { beginVoice() }
            return
        }
        guard connected else {
            if event.type == "error" { throw VoiceError.message("The lab did not accept this session. Reconnect from Lab connection.") }
            return
        }
        switch event.type {
        case "pong": if let seq = event.seq { heartbeat.pong(seq, now: ProcessInfo.processInfo.systemUptime) }
        case "state": if let state = event.state { try apply(state) }
        case "status":
            guard let status = event.status else { return }
            voiceStatus = status
            if ["listening", "speaking"].contains(status) && voiceWanted {
                providerReady = true; updateCapture()
            } else if ["unavailable", "reconnecting", "connecting"].contains(status) {
                providerReady = false; flushAudio(notify: true)
                if status == "unavailable" { voiceWanted = false; audio.stopAll(); notice = "Voice is unavailable. Continue with text, or try Talk again." }
            }
        case "transcript":
            if let role = event.role, let text = event.text, let turn = event.turnID {
                transcripts.update(role: role, text: text, turnID: turn, final: event.final ?? false); messages = transcripts.turns
            }
        case "reply_start":
            guard voiceWanted, foreground, !audioSuspended, !muted, let id = event.replyID else {
                if let id = event.replyID { fifo?.enqueue(.reply("interrupt", id: id)) }; return
            }
            if let previous = audio.activeReply { fifo?.enqueue(.reply("interrupt", id: previous)) }
            do { try audio.beginReply(id) }
            catch { voiceFailed(error) }
        case "audio":
            guard voiceWanted, !muted, foreground, !audioSuspended, let id = event.replyID, audio.activeReply == id else { return }
            guard let encoded = event.data, let bytes = Data(base64Encoded: encoded) else { voiceFailed(VoiceError.message("Voice sent unreadable audio.")); return }
            do { try audio.append(bytes, replyID: id) } catch { voiceFailed(error) }
        case "reply_end": if let id = event.replyID { audio.endReply(id) }
        case "interrupted":
            transcripts.discardPartialOutput(replyID: event.replyID)
            messages = transcripts.turns
            if event.replyID == nil || event.replyID == audio.activeReply { flushAudio(notify: false); updateCapture() }
        case "error":
            // Never render raw provider errors, which can contain remote URLs or credentials.
            notice = "The lab could not complete that step. Check the task status and try again."
            if event.recoverable == false || ["connection_revoked", "superseded", "owner_replaced"].contains(event.code ?? "") {
                wantsConnection = false; closeTransport(); connectionStatus = "Session opened elsewhere. Reconnect to continue."
            }
        default: break // Additive server events remain compatible.
        }
    }

    private func apply(_ state: LabSnapshot, restoring: Bool = false) throws {
        guard ["mock", "simulation", "mujoco"].contains(state.backend) else {
            throw VoiceError.message("This client supports mock and simulation sessions. Physical execution is unavailable.")
        }
        var privateState = state; privateState.accessToken = nil
        guard let acceptance = snapshotStore.accept(privateState) else { return }
        if acceptance == .newGeneration {
            // STOP and provider reconnect can advance generation without a new socket hello.
            // Remove the tap/converter and queued PCM before capture resumes under the new epoch.
            flushAudio(notify: true)
            acknowledgedProposal = nil
            presentationTask?.cancel(); presentingProposal = nil
        }
        if let prior = snapshot?.pending, let pending = privateState.pending,
           prior.id == pending.id, prior.reviewSummary != pending.reviewSummary {
            // A replacement preview must be displayed before it can be acknowledged.
            visibleProposal = nil
            acknowledgedProposal = nil
            presentationTask?.cancel(); presentingProposal = nil
        }
        snapshot = privateState
        if restoring { transcripts.restore(state.messages) } else { transcripts.reconcile(state.messages) }
        messages = transcripts.turns
        if acknowledgedProposal != state.pending?.id { acknowledgedProposal = nil }
        if let p = state.pending, visibleProposal == p.id { acknowledgeVisibleProposal(p) }
        updateCapture()
    }

    func proposalAppeared(_ proposal: Proposal) {
        guard snapshot?.pending?.id == proposal.id else { return }
        visibleProposal = proposal.id
        acknowledgeVisibleProposal(proposal)
    }
    func proposalDisappeared(_ id: String) {
        if visibleProposal == id { visibleProposal = nil }
    }
    private func isCurrent(_ proposal: Proposal) -> Bool {
        guard let snapshot, snapshot.generation == snapshotStore.audioGeneration else { return false }
        return proposal.matchesCurrent(snapshot.pending, generation: snapshot.generation, now: Date().timeIntervalSince1970)
    }

    private func acknowledgeVisibleProposal(_ proposal: Proposal) {
        guard connected, foreground, visibleProposal == proposal.id, isCurrent(proposal),
              acknowledgedProposal != proposal.id, presentingProposal != proposal.id,
              let origin, let credential, let attempt = connectionID, let generation = snapshot?.generation else { return }
        presentationTask?.cancel(); presentingProposal = proposal.id
        presentationTask = Task { [weak self] in
            guard let self else { return }
            defer {
                if self.connectionID == attempt, self.snapshot?.generation == generation, self.presentingProposal == proposal.id {
                    self.presentingProposal = nil
                }
            }
            do {
                // Allow the mounted SwiftUI card to draw; cancellation/visibility is rechecked.
                try await Task.sleep(for: .milliseconds(150))
                guard self.visibleProposal == proposal.id, self.foreground, self.connectionID == attempt,
                      self.snapshot?.generation == generation, self.isCurrent(proposal) else { return }
                var fields = proposal.fields; fields["channel"] = .string("text")
                let updated = try await self.request(url: AppEndpoint.sessionURL(origin, id: credential.sessionID, action: "present"), method: "POST", token: credential.accessToken, fields: fields)
                try Task.checkCancellation()
                guard self.connectionID == attempt, self.visibleProposal == proposal.id,
                      self.snapshot?.generation == generation, self.isCurrent(proposal) else { return }
                try self.apply(updated)
                if self.snapshot?.generation == generation && self.isCurrent(proposal) && self.snapshot?.pending?.presented == true {
                    self.acknowledgedProposal = proposal.id
                }
            } catch is CancellationError { }
            catch {
                if !Task.isCancelled, self.connectionID == attempt, self.snapshot?.generation == generation, self.isCurrent(proposal) {
                    self.notice = "The proposal could not be marked as shown. Reconnect before confirming."
                }
            }
        }
    }

    func chooseCondition(_ id: String) { act("condition", fields: ["condition_id": .string(id)]) }
    func predict(_ text: String) { if let text = clean(text) { act("prediction", fields: ["text": .string(text)]) } }
    func reflect(_ text: String) { if let text = clean(text) { act("reflection", fields: ["text": .string(text)]) } }
    @discardableResult
    func sendText(_ text: String) -> Bool {
        guard canAct, let request = DirectLabRequest(text) else { return false }
        act("request", fields: request.fields)
        return true
    }
    func confirm(_ proposal: Proposal) {
        guard canConfirm, isCurrent(proposal) else { return }
        act("confirm", fields: proposal.fields)
    }
    func cancel(_ proposal: Proposal) { act("cancel", fields: ["request_id": .string(proposal.requestID)]) }
    func cancelTask(_ id: String) { act("cancel", fields: ["request_id": .string(id)]) }
    func prepare() { act("prepare") }
    private func clean(_ text: String) -> String? { let s = text.trimmingCharacters(in: .whitespacesAndNewlines); return s.isEmpty ? nil : String(s.prefix(4000)) }

    private func act(_ action: String, fields: [String: JSONValue] = [:], emergency: Bool = false) {
        guard (canAct || emergency), let origin, let credential else { return }
        let attempt = connectionID
        if emergency { actionTask?.cancel() }
        let actionID = UUID()
        self.actionID = actionID
        busy = true; notice = nil
        actionTask = Task { [weak self] in
            guard let self else { return }
            defer { if self.actionID == actionID { self.actionID = nil; self.busy = false } }
            do {
                let state = try await self.request(url: AppEndpoint.sessionURL(origin, id: credential.sessionID, action: action), method: "POST", token: credential.accessToken, fields: fields)
                try Task.checkCancellation()
                guard self.connectionID == attempt, self.actionID == actionID else { return }
                try self.apply(state)
            } catch is CancellationError { }
            catch {
                guard self.connectionID == attempt, self.actionID == actionID else { return }
                let detail = self.actionError(error)
                self.notice = action == "stop" ? "Stop could not be confirmed. \(detail)" : detail
                // Reconcile ambiguous HTTP outcomes; never replay a command or confirmation.
                if let state = try? await self.request(url: AppEndpoint.sessionURL(origin, id: credential.sessionID), method: "GET", token: credential.accessToken),
                   self.connectionID == attempt, self.actionID == actionID {
                    try? self.apply(state)
                }
            }
        }
    }

    func stopLab() {
        stopVoice()
        guard origin != nil, credential != nil else {
            notice = "Connect to the lab to send Stop."
            return
        }
        act("stop", emergency: true) // Direct deterministic endpoint; never asks a provider to stop.
    }

    func toggleVoice() {
        if voiceWanted { stopVoice(); return }
        guard connected, foreground else { notice = "Connect to your lab first. You can use text without microphone permission."; return }
        voiceTask?.cancel()
        voiceTask = Task { [weak self] in
            guard let self else { return }
            let granted = await withCheckedContinuation { continuation in
                AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
            }
            guard !Task.isCancelled, self.foreground, self.connected else { return }
            self.needsMicrophoneSettings = !granted
            guard granted else { self.notice = "Microphone access is off. Allow it in Settings, or continue with text."; return }
            self.voiceWanted = true; self.muted = false; self.notice = nil; self.beginVoice()
        }
    }

    private func beginVoice() {
        guard voiceWanted, connected, foreground, !audioSuspended else { return }
        do {
            try audio.activate()
            voiceStatus = "connecting"; providerReady = false
            fifo?.enqueue(ClientFrame(type: "start_voice")); fifo?.enqueue(.mute(muted))
        } catch { voiceFailed(error) }
    }
    func stopVoice() {
        voiceTask?.cancel(); voiceTask = nil
        audioRecoveryTask?.cancel(); audioRecoveryTask = nil
        voiceWanted = false; providerReady = false; voiceStatus = "off"
        flushAudio(notify: true); audio.stopAll()
        fifo?.enqueue(ClientFrame(type: "stop_voice"))
    }
    func toggleMute() {
        guard voiceWanted else { return }
        muted.toggle()
        flushAudio(notify: true)
        fifo?.enqueue(.mute(muted))
        updateCapture()
    }
    func interrupt() {
        flushAudio(notify: true)
        updateCapture()
    }
    private func updateCapture() {
        guard voiceWanted, providerReady, foreground, !audioSuspended, !muted, connected, let fifo, let generation = snapshotStore.audioGeneration else {
            fifo?.stopCaptureAndDiscardAudio(); audio.stopCapture(); microphoneActive = false; return
        }
        do {
            try audio.startCapture(into: fifo, generation: generation)
            microphoneActive = audio.isCapturing
        } catch { voiceFailed(error) }
    }
    private func flushAudio(notify: Bool) {
        fifo?.stopCaptureAndDiscardAudio(); audio.stopCapture(); microphoneActive = false
        if let id = audio.interruptPlayback(), notify { fifo?.enqueue(.reply("interrupt", id: id)) }
        speakerActive = false
        transcripts.discardPartialInput()
        transcripts.discardPartialOutput()
        messages = transcripts.turns
    }
    private func voiceFailed(_ error: Error) {
        stopVoice(); voiceStatus = "unavailable"
        notice = "Voice paused. Check microphone access and audio output, then try Talk again. Text remains available."
    }

    func setForeground(_ active: Bool) {
        guard foreground != active else { return }
        foreground = active
        if !active {
            closeTransport()
            connectionStatus = "Your lab is saved. Audio is paused."
        } else if wantsConnection {
            audioSuspended = false; retryCount = 0; startConnection()
        }
    }
    private func interruption(raw: UInt?, options: UInt) {
        guard let raw, let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        if type == .began {
            audioSuspended = true; providerReady = false; flushAudio(notify: true); audio.stopAll()
            fifo?.enqueue(ClientFrame(type: "stop_voice")); voiceStatus = "paused"
        } else {
            audioSuspended = false
            if AVAudioSession.InterruptionOptions(rawValue: options).contains(.shouldResume) { beginVoice() }
            else { stopVoice() }
        }
    }
    private func routeChanged(_ raw: UInt) {
        guard let reason = AVAudioSession.RouteChangeReason(rawValue: raw),
              [.newDeviceAvailable, .oldDeviceUnavailable, .routeConfigurationChange].contains(reason) else { return }
        recoverAudio()
    }
    private func recoverAudio() {
        guard voiceWanted, foreground else { return }
        flushAudio(notify: true); audio.stopAll(); providerReady = false
        fifo?.enqueue(ClientFrame(type: "stop_voice")); voiceStatus = "connecting"
        audioRecoveryTask?.cancel()
        audioRecoveryTask = Task { [weak self] in
            do { try await Task.sleep(for: .milliseconds(350)) } catch { return }
            self?.beginVoice()
        }
    }

    func disconnect() {
        let saved = credential; let endpoint = origin
        wantsConnection = false; voiceWanted = false; closeTransport()
        connectionStatus = "Your lab is saved"
        if let saved, let endpoint {
            actionTask = Task { [weak self] in
                guard let self else { return }
                _ = try? await self.request(url: AppEndpoint.sessionURL(endpoint, id: saved.sessionID, action: "disconnect"), method: "POST", token: saved.accessToken, fields: [:])
            }
        }
    }

    private func connectionFailed(_ error: Error) {
        if socket?.closeCode.rawValue == 4001 {
            wantsConnection = false
            closeTransport()
            connectionStatus = "Session opened elsewhere. Reconnect to continue."
            return
        }
        let terminal: Bool
        if let e = error as? HTTPFailure { terminal = [401, 403, 404, 409, 426].contains(e.code) }
        else { terminal = error is DecodingError || error is VoiceError }
        closeTransport()
        guard foreground, wantsConnection else { return }
        guard !terminal, retryCount < 4 else {
            connecting = false; connectionStatus = "Lab connection paused"
            notice = actionError(error); return
        }
        retryCount += 1; connecting = true
        if let queueError = error as? CaptureQueueFailure { notice = queueError.message }
        connectionStatus = "Reconnecting · attempt \(retryCount) of 4"
        let delay = pow(2.0, Double(retryCount - 1))
        retryTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(delay)) } catch { return }
            self?.startConnection()
        }
    }

    /// The sole teardown owner. Every stale callback is invalidated before resources are stopped.
    private func closeTransport() {
        connectionID = nil; connected = false; connecting = false
        startupTask?.cancel(); startupTask = nil
        readerTask?.cancel(); readerTask = nil
        writerTask?.cancel(); writerTask = nil
        heartbeatTask?.cancel(); heartbeatTask = nil
        retryTask?.cancel(); retryTask = nil
        actionTask?.cancel(); actionTask = nil; actionID = nil; busy = false
        presentationTask?.cancel(); presentationTask = nil; presentingProposal = nil
        voiceTask?.cancel(); voiceTask = nil
        audioRecoveryTask?.cancel(); audioRecoveryTask = nil
        flushAudio(notify: false); audio.stopAll()
        fifo?.close(); fifo = nil
        socket?.cancel(with: .goingAway, reason: nil); socket = nil
        providerReady = false; voiceStatus = voiceWanted ? "reconnecting" : "off"
        acknowledgedProposal = nil; visibleProposal = nil
        transcripts.restore(snapshot?.messages ?? []); messages = transcripts.turns
    }

    private func actionError(_ error: Error) -> String {
        if let e = error as? HTTPFailure {
            switch e.code {
            case 401, 403: return "The lab did not accept the credential. Check your pairing code in Lab connection."
            case 404: return "This session is no longer available. Reconnect to open a new lab."
            case 409, 422: return "The trial changed or this step is not ready. Review the current proposal before trying again."
            default: return "The lab could not complete that step. The command was not repeated. Reconnect or try again."
            }
        }
        if error is DecodingError { return "The lab response did not match this client. Check that the server uses protocol version 1." }
        if let queueError = error as? CaptureQueueFailure { return queueError.message }
        if let e = error as? VoiceError { return e.localizedDescription }
        let code = (error as NSError).code
        switch code {
        case NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed: return "The lab address could not be found. Check the server address and Wi-Fi."
        case NSURLErrorSecureConnectionFailed, NSURLErrorServerCertificateUntrusted, NSURLErrorServerCertificateHasBadDate, NSURLErrorServerCertificateHasUnknownRoot:
            return "The lab’s HTTPS certificate could not be verified. Use the trusted HTTPS address."
        case NSURLErrorAppTransportSecurityRequiresSecureConnection: return "iOS blocked this address. Use trusted HTTPS, or a .local development host with local networking permission."
        default: return "The lab is unreachable. Check Wi-Fi and the server, then reconnect. Your commands will not be replayed."
        }
    }
}
