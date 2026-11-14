import Foundation

enum VoiceError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        if case let .message(text) = self { return text }
        return nil
    }
}

enum RelayEndpoint {
    static func resolve(_ input: String) throws -> URL {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let isHostname = !text.contains("://")
        guard !text.isEmpty, !text.contains(where: { $0.isWhitespace }),
              var parts = URLComponents(string: isHostname ? "ws://\(text)" : text),
              let scheme = parts.scheme?.lowercased(), ["ws", "wss"].contains(scheme),
              let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.port.map({ (1...65535).contains($0) }) ?? true else {
            throw VoiceError.message("Enter a hostname such as mac-name.local, or a ws:// or wss:// URL without credentials, a query, or a fragment.")
        }
        parts.scheme = scheme
        if isHostname && parts.port == nil { parts.port = 8765 }
        if parts.path.isEmpty || parts.path == "/" { parts.path = "/voice" }
        guard let url = parts.url else { throw VoiceError.message("The relay address is invalid.") }
        return url
    }
}

struct ServerEvent: Decodable {
    let type: String
    var sessionID: String?
    var mode: String?
    var logging: Bool?
    var rawAudio: Bool?
    var state: String?
    var turnID: String?
    var text: String?
    var role: String?
    var message: String?
    var fatal: Bool?

    enum CodingKeys: String, CodingKey {
        case type, mode, logging, state, text, role, message, fatal
        case sessionID = "session_id", rawAudio = "raw_audio", turnID = "turn_id"
    }
}

enum ClientControl {
    case mute(Bool), played(String), ping, end

    var json: String {
        var object: [String: Any]
        switch self {
        case let .mute(value): object = ["type": "mute", "muted": value]
        case let .played(turn): object = ["type": "played", "turn_id": turn]
        case .ping: object = ["type": "ping"]
        case .end: object = ["type": "end"]
        }
        // Every value above is a JSON primitive; serialization cannot fail.
        let data = try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self)
    }
}

/// Server permission and local intent must both allow capture. Resume never grants permission.
struct CaptureGate {
    private(set) var muted = false
    private(set) var serverListening = false
    private(set) var replyPending = false
    var canCapture: Bool { serverListening && !muted && !replyPending }

    mutating func setMuted(_ value: Bool) { muted = value; serverListening = false }
    mutating func receiveState(_ state: String) throws {
        guard ["processing", "listening", "muted"].contains(state) else {
            throw VoiceError.message("The relay sent an unsupported conversation state.")
        }
        serverListening = state == "listening"
    }
    mutating func beginReply() { replyPending = true; serverListening = false }
    mutating func finishReply() { replyPending = false; serverListening = false }
}

/// The only outgoing frame queue. Its lock also closes the capture gate atomically on mute.
/// Audio callbacks write here directly: no unbounded DispatchQueue/Task backlog of PCM buffers.
final class OutboundFIFO: @unchecked Sendable {
    enum Frame {
        case audio(Data)
        case control(String, endsSession: Bool)
        var byteCount: Int {
            switch self {
            case let .audio(data): return data.count
            case let .control(text, _): return text.utf8.count
            }
        }
        var isAudio: Bool { if case .audio = self { return true }; return false }
    }

    let wakeups: AsyncStream<Void>
    private let continuation: AsyncStream<Void>.Continuation
    private let lock = NSLock()
    private let maxFrames: Int
    private let maxBytes: Int
    private var frames: [Frame] = []
    private var bytes = 0
    private var captureToken: UUID?
    private var closed = false
    private var problem: String?

    init(maxFrames: Int = 64, maxBytes: Int = 256 * 1024) {
        self.maxFrames = maxFrames
        self.maxBytes = maxBytes
        let pair = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
        wakeups = pair.stream
        continuation = pair.continuation
    }

    var failure: String? { lock.withLock { problem } }
    var count: Int { lock.withLock { frames.count } }
    var byteCount: Int { lock.withLock { bytes } }

    func beginCapture() -> UUID {
        lock.withLock {
            let token = UUID()
            if !closed { captureToken = token }
            return token
        }
    }

    func stopCaptureAndDiscardAudio() {
        lock.withLock {
            captureToken = nil
            frames.removeAll(where: { $0.isAudio })
            bytes = frames.reduce(0) { $0 + $1.byteCount }
        }
    }

    func enqueueAudio(_ data: Data, token: UUID) {
        let changed = lock.withLock {
            guard !closed, problem == nil, captureToken == token, !data.isEmpty else { return false }
            return appendLocked(.audio(data))
        }
        if changed { continuation.yield(()) }
    }

    func enqueue(_ control: ClientControl) {
        let ends: Bool
        if case .end = control { ends = true } else { ends = false }
        let changed = lock.withLock {
            guard !closed, problem == nil else { return false }
            return appendLocked(.control(control.json, endsSession: ends))
        }
        if changed { continuation.yield(()) }
    }

    private func appendLocked(_ frame: Frame) -> Bool {
        guard frames.count < maxFrames, bytes + frame.byteCount <= maxBytes else {
            problem = "The network cannot keep up with microphone audio. Move closer to Wi-Fi and start a new session."
            captureToken = nil
            frames.removeAll()
            bytes = 0
            return true
        }
        frames.append(frame)
        bytes += frame.byteCount
        return true
    }

    func fail(_ message: String, captureToken token: UUID? = nil) {
        lock.withLock {
            // A removed tap may finish conversion after mute or a later capture starts.
            guard !closed, problem == nil, token == nil || captureToken == token else { return }
            problem = message
            captureToken = nil
            frames.removeAll()
            bytes = 0
        }
        continuation.yield(())
    }

    func pop() -> Frame? {
        lock.withLock {
            guard !closed, problem == nil, !frames.isEmpty else { return nil }
            let first = frames.removeFirst()
            bytes -= first.byteCount
            return first
        }
    }

    func close() {
        lock.withLock {
            closed = true
            captureToken = nil
            frames.removeAll()
            bytes = 0
        }
        continuation.finish()
    }
}

enum PCMBytes {
    /// Explicit byte order; no reliance on the native CPU's endianness.
    static func littleEndian(_ samples: UnsafeBufferPointer<Int16>) -> Data {
        var data = Data(count: samples.count * 2)
        data.withUnsafeMutableBytes { raw in
            let output = raw.bindMemory(to: UInt8.self)
            for (index, value) in samples.enumerated() {
                let bits = UInt16(bitPattern: value)
                output[index * 2] = UInt8(truncatingIfNeeded: bits)
                output[index * 2 + 1] = UInt8(truncatingIfNeeded: bits >> 8)
            }
        }
        return data
    }
}

enum WaveFile {
    static let maximumBytes = 8 * 1024 * 1024

    /// Accept one complete RIFF/WAVE containing mono integer PCM. The rate is chosen by the relay.
    static func validate(_ data: Data) throws {
        func invalid() -> VoiceError { .message("The relay reply is not a complete mono PCM WAV file. Start a new session.") }
        guard data.count >= 44, data.count <= maximumBytes else { throw invalid() }
        let bytes = [UInt8](data)
        func tag(_ offset: Int) -> String { String(decoding: bytes[offset..<(offset + 4)], as: UTF8.self) }
        func u16(_ offset: Int) -> Int { Int(bytes[offset]) | Int(bytes[offset + 1]) << 8 }
        func u32(_ offset: Int) -> Int { u16(offset) | u16(offset + 2) << 16 }
        guard tag(0) == "RIFF", tag(8) == "WAVE", u32(4) + 8 == bytes.count else { throw invalid() }
        var offset = 12
        var alignment: Int?
        var payloadSize: Int?
        while offset + 8 <= bytes.count {
            let kind = tag(offset)
            let size = u32(offset + 4)
            let start = offset + 8
            guard size <= bytes.count - start else { throw invalid() }
            if kind == "fmt " {
                guard alignment == nil, size >= 16, u16(start) == 1, u16(start + 2) == 1,
                      (1...192_000).contains(u32(start + 4)),
                      [8, 16, 24, 32].contains(u16(start + 14)),
                      u16(start + 12) == u16(start + 14) / 8,
                      u32(start + 8) == u32(start + 4) * u16(start + 12) else { throw invalid() }
                alignment = u16(start + 12)
            } else if kind == "data" {
                guard payloadSize == nil, size > 0 else { throw invalid() }
                payloadSize = size
            }
            offset = start + size + (size % 2)
        }
        guard offset == bytes.count, let alignment, let payloadSize, payloadSize % alignment == 0 else {
            throw invalid()
        }
    }
}
