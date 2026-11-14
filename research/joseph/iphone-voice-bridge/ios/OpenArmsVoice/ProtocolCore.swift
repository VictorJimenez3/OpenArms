import Foundation

// Foundation-only contract and state machines; shared by the app and offline tests.
enum VoiceError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case let .message(text) = self { return text }; return nil }
}

enum AppEndpoint {
    static func resolve(_ input: String, allowLocalDebug: Bool = false) throws -> URL {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !text.contains(where: \.isWhitespace),
              var parts = URLComponents(string: text), let scheme = parts.scheme?.lowercased(),
              let host = parts.host?.lowercased(), !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/",
              parts.port.map({ (1...65535).contains($0) }) ?? true,
              scheme == "https" || (scheme == "http" && allowLocalDebug && isLocal(host)) else {
            throw VoiceError.message("Enter the trusted HTTPS server origin, for example https://lab.example.org. Local HTTP needs the explicit development switch.")
        }
        parts.scheme = scheme; parts.host = host; parts.path = ""
        guard let url = parts.url else { throw VoiceError.message("Invalid server address.") }
        return url
    }

    static func isLocal(_ host: String) -> Bool {
        if ["localhost", "[::1]", "::1"].contains(host) || host.hasSuffix(".local") { return true }
        let components = host.split(separator: ".")
        guard components.count == 4, components.allSatisfy({ UInt8($0) != nil }) else { return false }
        let values = components.compactMap { UInt8($0) }
        return values[0] == 10 || values[0] == 127 || (values[0] == 192 && values[1] == 168)
            || (values[0] == 172 && (16...31).contains(values[1]))
    }

    static func sessionURL(_ origin: URL, id: String, action: String? = nil) throws -> URL {
        guard !id.isEmpty, id.count <= 200,
              id.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.contains($0) || "-_".unicodeScalars.contains($0) }) else {
            throw VoiceError.message("The server returned an invalid session identifier.")
        }
        let url = origin.appendingPathComponent("api/sessions").appendingPathComponent(id)
        return action.map { url.appendingPathComponent($0) } ?? url
    }

    static func liveURL(_ origin: URL, id: String) throws -> URL {
        var parts = URLComponents(url: try sessionURL(origin, id: id, action: "live"), resolvingAgainstBaseURL: false)!
        parts.scheme = origin.scheme == "https" ? "wss" : "ws"
        return parts.url!
    }
}

struct SessionCredential: Codable, Equatable {
    let origin: String
    let sessionID: String
    let accessToken: String
}

struct LabSnapshot: Decodable, Equatable {
    let sessionID: String
    let backend: String
    let revision: Int
    let generation: Int
    let connected: Bool
    let experiment: Experiment
    let trial: Trial
    let conditions: [Condition]
    let prediction: String
    let pending: Proposal?
    let observations: [Observation]
    let messages: [LabMessage]
    let notebook: [JSONValue]
    let state: JSONValue
    var accessToken: String?
    // Optional server-owned records. Keep their original associations/provenance, including nulls.
    let task: JSONValue?
    let tasks: JSONValue?
    let scene: JSONValue?
    let sceneEvidence: JSONValue?
    let sceneImages: JSONValue?
    let skills: JSONValue?
    let executionReceipts: JSONValue?
    let outcomes: JSONValue?
    let evaluations: JSONValue?

    var taskRecords: [JSONValue] { RecordPresentation.records(tasks) + RecordPresentation.records(task) }
    var sceneRecords: [JSONValue] { RecordPresentation.records(sceneEvidence) + RecordPresentation.records(scene) }
    var imageRecords: [JSONValue] { RecordPresentation.records(sceneImages) }
    var skillRecords: [JSONValue] { RecordPresentation.records(skills) }
    var executionRecords: [JSONValue] {
        RecordPresentation.records(executionReceipts) + taskRecords.flatMap { RecordPresentation.records($0["execution"]) }
    }
    var outcomeRecords: [JSONValue] { RecordPresentation.records(outcomes) }
    var evaluationRecords: [JSONValue] {
        RecordPresentation.records(evaluations) + notebook.compactMap {
            $0["kind"]?.string == "skill_evaluation" ? $0["data"] : nil
        }
    }
    func latestProgress(for task: JSONValue) -> JSONValue? {
        guard task["status"]?.string == "executing", let id = task["task_id"]?.string else { return nil }
        // Keep progress associated with the task's current proposal.
        let request = task["request_id"]?.string
        return notebook.reversed().lazy.compactMap { event in
            event["kind"]?.string == "execution_progress" ? event["data"] : nil
        }.first {
            $0["task_id"]?.string == id && $0["request_id"]?.string == request
        }
    }

    enum CodingKeys: String, CodingKey {
        case backend, revision, generation, connected, experiment, trial, conditions, prediction, pending, observations, messages, notebook, state
        case task, tasks, scene, skills, outcomes, evaluations
        case sceneEvidence = "scene_evidence", sceneImages = "scene_images", executionReceipts = "execution_receipts"
        case sessionID = "session_id", accessToken = "access_token"
    }
}
struct Experiment: Decodable, Equatable { let id: String; let title: String; let question: String }
struct Trial: Decodable, Equatable {
    let trialID: String
    let conditionID: String?
    let state: String
    enum CodingKeys: String, CodingKey { case state, trialID = "trial_id", conditionID = "condition_id" }
}
struct Condition: Decodable, Equatable, Identifiable { let id: String; let title: String }
struct Proposal: Decodable, Equatable, Identifiable {
    let requestID: String
    let proposalVersion: Int
    let summary: String
    let conditionID: String?
    let planHash: String?
    let skillID: String?
    let skillVersion: JSONValue?
    let status: String
    let presented: Bool
    var id: String { "\(requestID):\(proposalVersion)" }
    enum CodingKeys: String, CodingKey {
        case summary, status, presented
        case requestID = "request_id", proposalVersion = "proposal_version", conditionID = "condition_id"
        case planHash = "plan_hash", skillID = "skill_id", skillVersion = "skill_version"
    }
    var fields: [String: JSONValue] { ["request_id": .string(requestID), "proposal_version": .number(Double(proposalVersion))] }
}
struct Observation: Decodable, Equatable, Identifiable {
    let observationID: String?
    let requestID: String
    let trialID: String
    let provenance: String
    let text: String
    let source: String
    let evidence: [JSONValue]
    var id: String { observationID ?? "\(trialID):\(requestID)" }
    enum CodingKeys: String, CodingKey {
        case provenance, text, source, evidence, observationID = "observation_id", requestID = "request_id", trialID = "trial_id"
    }
}
struct LabMessage: Decodable, Equatable, Identifiable {
    var messageID: String?
    let role: String
    var text: String
    let turnID: String?
    var final: Bool? = nil
    var id: String { turnID.map { "\(role):\($0)" } ?? messageID ?? "\(role):\(text)" }
    enum CodingKeys: String, CodingKey { case role, text, final, messageID = "id", turnID = "turn_id" }
}

// Preserve arbitrary notebook/evidence fields without coupling the client to server internals.
indirect enum JSONValue: Codable, Equatable {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case let .string(v): try c.encode(v)
        case let .number(v): try c.encode(v)
        case let .bool(v): try c.encode(v)
        case let .array(v): try c.encode(v)
        case let .object(v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    subscript(_ key: String) -> JSONValue? { if case let .object(v) = self { return v[key] }; return nil }
    var string: String? { if case let .string(v) = self { return v }; return nil }
    var scalarText: String? {
        switch self {
        case let .string(v): return v.isEmpty ? nil : v
        case let .number(v): return Int(exactly: v).map(String.init) ?? String(v)
        case let .bool(v): return v ? "Yes" : "No"
        default: return nil
        }
    }
}

/// Read-only prose adapter, never infers status, success, provenance or skill activation.
enum RecordPresentation {
    static func records(_ value: JSONValue?) -> [JSONValue] {
        switch value {
        case let .array(values): return values.filter { if case .object = $0 { return true }; return false }
        case .object: return value.map { [$0] } ?? []
        default: return []
        }
    }
    static func text(_ record: JSONValue, _ keys: String...) -> String? {
        keys.lazy.compactMap { record[$0]?.scalarText }.first
    }
    static func status(_ record: JSONValue) -> String? {
        text(record, "status", "lifecycle", "state")?.replacingOccurrences(of: "_", with: " ")
    }
    static func provenance(_ record: JSONValue) -> String {
        text(record, "provenance") ?? "Provenance not supplied"
    }
    static func clarification(_ record: JSONValue) -> String? {
        guard record["status"]?.string == "needs_clarification" else { return nil }
        return text(record, "clarification", "question") ?? record["clarification"]?["question"]?.string ??
            text(record, "summary")
    }
}

struct ServerEvent: Decodable {
    let type: String
    var protocolVersion: Int?
    var connectionID: String?
    var generation: Int?
    var seq: Int?
    var state: LabSnapshot?
    var status: String?
    var message: String?
    var code: String?
    var recoverable: Bool?
    var role: String?
    var text: String?
    var turnID: String?
    var final: Bool?
    var replyID: String?
    var proposal: ReplyProposal?
    var data: String?
    enum CodingKeys: String, CodingKey {
        case type, generation, seq, state, status, message, code, recoverable, role, text, final, proposal, data
        case protocolVersion = "protocol_version", connectionID = "connection_id", turnID = "turn_id", replyID = "reply_id"
    }
}
struct ReplyProposal: Decodable, Equatable {
    let requestID: String
    let proposalVersion: Int
    enum CodingKeys: String, CodingKey { case requestID = "request_id", proposalVersion = "proposal_version" }
}

struct ClientFrame {
    let type: String
    var fields: [String: JSONValue] = [:]
    var json: String {
        var object = fields; object["type"] = .string(type)
        return String(decoding: try! JSONEncoder().encode(object), as: UTF8.self)
    }
    static func hello(id: UUID, token: String) -> Self {
        Self(type: "hello", fields: ["protocol_version": .number(1), "connection_id": .string(id.uuidString), "access_token": .string(token)])
    }
    static func reply(_ type: String, id: String) -> Self { Self(type: type, fields: ["reply_id": .string(id)]) }
    static func mute(_ value: Bool) -> Self { Self(type: "mute", fields: ["muted": .bool(value)]) }
}

struct SnapshotStore {
    enum Acceptance { case sameGeneration, newGeneration }

    private(set) var value: LabSnapshot?
    private(set) var audioGeneration: Int?
    mutating func acceptHello(generation: Int) -> Bool {
        guard generation >= 0, generation >= (audioGeneration ?? 0), generation >= (value?.generation ?? 0) else { return false }
        audioGeneration = generation
        return true
    }
    mutating func accept(_ snapshot: LabSnapshot) -> Acceptance? {
        guard snapshot.generation >= (audioGeneration ?? 0) else { return nil }
        if let old = value {
            guard snapshot.sessionID == old.sessionID, snapshot.revision >= old.revision,
                  snapshot.generation >= old.generation else { return nil }
        }
        let acceptance: Acceptance = audioGeneration == snapshot.generation ? .sameGeneration : .newGeneration
        value = snapshot
        audioGeneration = snapshot.generation
        return acceptance
    }
}

struct TranscriptStore {
    private(set) var turns: [LabMessage] = []
    mutating func restore(_ messages: [LabMessage]) {
        turns = []
        // Live partials belong to the current audio generation, not to restored history.
        for message in messages where message.final != false {
            if let index = turns.firstIndex(where: { $0.id == message.id }) { turns[index] = message }
            else { turns.append(message) }
        }
    }
    mutating func update(role: String, text: String, turnID: String, final: Bool) {
        guard ["user", "assistant"].contains(role), !text.isEmpty, !turnID.isEmpty else { return }
        let id = "\(role):\(turnID)"
        if let index = turns.firstIndex(where: { $0.id == id }) {
            guard turns[index].final == false else { return }
            let previous = turns[index].text
            if final || text.hasPrefix(previous) { turns[index].text = text }
            else if !previous.hasSuffix(text) { turns[index].text += text }
            turns[index].final = final
        } else { turns.append(LabMessage(role: role, text: text, turnID: turnID, final: final)) }
        if turns.count > 150 { turns.removeFirst(turns.count - 150) }
    }
    mutating func discardPartialInput() {
        turns.removeAll { $0.role == "user" && $0.final == false }
    }
    // State broadcasts may lag a live turn; preserve only live turns absent from canonical history.
    mutating func reconcile(_ messages: [LabMessage]) {
        let ids = Set(messages.filter { $0.final != false }.map(\.id))
        let live = turns.filter { !ids.contains($0.id) }
        restore(messages)
        turns.append(contentsOf: live)
    }
}

/// A played acknowledgment requires reply_end AND every dataPlayedBack callback, at least once.
struct PlaybackLedger {
    private(set) var replyID: String?
    private(set) var pending: Set<UUID> = []
    private(set) var scheduled = 0
    private(set) var ended = false
    mutating func begin(_ id: String) { replyID = id; pending = []; scheduled = 0; ended = false }
    mutating func schedule(_ id: String) -> UUID? {
        guard replyID == id, !ended else { return nil }
        let token = UUID(); pending.insert(token); scheduled += 1; return token
    }
    mutating func finish(_ id: String) -> String? { guard replyID == id else { return nil }; ended = true; return completed() }
    mutating func played(_ token: UUID, reply id: String) -> String? {
        guard replyID == id, pending.remove(token) != nil else { return nil }; return completed()
    }
    private mutating func completed() -> String? {
        guard ended, scheduled > 0, pending.isEmpty, let id = replyID else { return nil }
        invalidate(); return id
    }
    mutating func invalidate() { replyID = nil; pending = []; scheduled = 0; ended = false }
}

struct Heartbeat {
    private(set) var sequence = 0
    private(set) var lastPong: TimeInterval
    private var outstanding: Set<Int> = []
    init(now: TimeInterval) { lastPong = now }
    mutating func ping() -> Int { sequence += 1; outstanding.insert(sequence); return sequence }
    mutating func pong(_ seq: Int, now: TimeInterval) {
        guard outstanding.contains(seq) else { return }
        outstanding = outstanding.filter { $0 > seq }; lastPong = now
    }
    func expired(now: TimeInterval) -> Bool { now - lastPong >= 15 }
}

/// One bounded, synchronized queue; tap callbacks cannot build an unbounded Task backlog.
final class OutboundFIFO: @unchecked Sendable {
    enum Frame {
        case audio(Data, epoch: Int), control(String)
        var isAudio: Bool { if case .audio = self { return true }; return false }
        var byteCount: Int { switch self { case let .audio(d, _): return d.count * 2; case let .control(s): return s.utf8.count } }
        var json: String {
            switch self {
            case let .control(s): return s
            case let .audio(d, epoch): return ClientFrame(type: "audio", fields: ["data": .string(d.base64EncodedString()), "epoch": .number(Double(epoch))]).json
            }
        }
    }
    let wakeups: AsyncStream<Void>
    private let continuation: AsyncStream<Void>.Continuation
    private let lock = NSLock()
    private var frames: [Frame] = []
    private var bytes = 0
    private var captureToken: UUID?
    private var epoch = 0
    private var closed = false
    private var problem: String?
    private let maxFrames: Int
    private let maxBytes: Int
    init(maxFrames: Int = 64, maxBytes: Int = 256 * 1024) {
        self.maxFrames = maxFrames; self.maxBytes = maxBytes
        let pair = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
        wakeups = pair.stream; continuation = pair.continuation
    }
    var failure: String? { lock.withLock { problem } }
    var count: Int { lock.withLock { frames.count } }
    func beginCapture(epoch: Int) -> UUID {
        lock.withLock { let id = UUID(); if !closed { captureToken = id; self.epoch = epoch }; return id }
    }
    func stopCaptureAndDiscardAudio() {
        lock.withLock { captureToken = nil; frames.removeAll(where: \.isAudio); bytes = frames.reduce(0) { $0 + $1.byteCount } }
    }
    func enqueueAudio(_ data: Data, token: UUID) {
        let changed = lock.withLock {
            guard !closed, problem == nil, captureToken == token, !data.isEmpty, data.count % 2 == 0, data.count <= 6400 else { return false }
            return appendLocked(.audio(data, epoch: epoch))
        }
        if changed { continuation.yield(()) }
    }
    func enqueue(_ frame: ClientFrame) {
        let changed = lock.withLock { !closed && problem == nil ? appendLocked(.control(frame.json)) : false }
        if changed { continuation.yield(()) }
    }
    private func appendLocked(_ frame: Frame) -> Bool {
        guard frames.count < maxFrames, bytes + frame.byteCount <= maxBytes else {
            problem = "Audio paused because the network could not keep up. Reconnecting…"
            captureToken = nil; frames = []; bytes = 0; return true
        }
        frames.append(frame); bytes += frame.byteCount; return true
    }
    func fail(_ message: String, token: UUID) {
        lock.withLock {
            guard !closed, captureToken == token else { return }
            problem = message; captureToken = nil; frames = []; bytes = 0
        }
        continuation.yield(())
    }
    func pop() -> Frame? {
        lock.withLock { guard !closed, problem == nil, !frames.isEmpty else { return nil }; let f = frames.removeFirst(); bytes -= f.byteCount; return f }
    }
    func close() { lock.withLock { closed = true; captureToken = nil; frames = []; bytes = 0 }; continuation.finish() }
}

enum PCMBytes {
    static func littleEndian(_ samples: UnsafeBufferPointer<Int16>) -> Data {
        var data = Data(count: samples.count * 2)
        data.withUnsafeMutableBytes { raw in
            let out = raw.bindMemory(to: UInt8.self)
            for (i, value) in samples.enumerated() {
                let bits = UInt16(bitPattern: value); out[i * 2] = UInt8(truncatingIfNeeded: bits); out[i * 2 + 1] = UInt8(truncatingIfNeeded: bits >> 8)
            }
        }; return data
    }
    static func floats(_ data: Data) throws -> [Float] {
        guard !data.isEmpty, data.count % 2 == 0, data.count <= 480_000 else { throw VoiceError.message("Invalid streamed audio.") }
        let b = [UInt8](data)
        return stride(from: 0, to: b.count, by: 2).map { Float(Int16(bitPattern: UInt16(b[$0]) | UInt16(b[$0 + 1]) << 8)) / 32768 }
    }
}
