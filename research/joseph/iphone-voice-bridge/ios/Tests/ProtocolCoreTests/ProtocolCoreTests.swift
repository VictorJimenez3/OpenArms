import Foundation
import XCTest
@testable import VoiceProtocol

final class ProtocolCoreTests: XCTestCase {
    func testTrustedOriginAndSessionURLs() throws {
        let origin = try AppEndpoint.resolve(" HTTPS://Lab.Example.org/ ")
        XCTAssertEqual(origin.absoluteString, "https://lab.example.org")
        XCTAssertEqual(try AppEndpoint.liveURL(origin, id: "session-1").absoluteString,
                       "wss://lab.example.org/api/sessions/session-1/live")
        XCTAssertThrowsError(try AppEndpoint.sessionURL(origin, id: "../other"))
        for address in ["", "lab.example.org", "ws://lab.local", "http://lab.local",
                        "https://user:pass@host", "https://host?token=x", "https://host/#fragment",
                        "https://host/path", "https://host:0", "https://bad host"] {
            XCTAssertThrowsError(try AppEndpoint.resolve(address), address)
        }
        for address in ["http://lab.local:8765", "http://127.0.0.1:8765", "http://[::1]:8765", "http://192.168.1.2"] {
            XCTAssertNoThrow(try AppEndpoint.resolve(address, allowLocalDebug: true))
        }
        XCTAssertThrowsError(try AppEndpoint.resolve("http://example.org", allowLocalDebug: true))
    }

    func testStreamingControlFramesUseHelloCredentialAndReplyID() throws {
        let connection = UUID()
        let hello = try fields(ClientFrame.hello(id: connection, token: "fixture-token").json)
        XCTAssertEqual(hello, ["type": .string("hello"), "protocol_version": .number(1),
                               "connection_id": .string(connection.uuidString), "access_token": .string("fixture-token")])
        let reply = "reply-\"\\\n"
        XCTAssertEqual(try fields(ClientFrame.reply("played", id: reply).json),
                       ["type": .string("played"), "reply_id": .string(reply)])
        let event = try decode(ServerEvent.self, """
        {"type":"reply_start","reply_id":"r1","proposal":{"request_id":"p1","proposal_version":3}}
        """)
        XCTAssertEqual(event.replyID, "r1")
        XCTAssertEqual(event.proposal?.requestID, "p1")
        XCTAssertEqual(event.proposal?.proposalVersion, 3)
    }

    func testAcceptedSnapshotRotatesCaptureEpochWithoutSocketHello() throws {
        var snapshots = SnapshotStore()
        var transcript = TranscriptStore()
        let queue = OutboundFIFO()
        XCTAssertTrue(snapshots.acceptHello(generation: 2))
        XCTAssertEqual(snapshots.accept(try snapshot(revision: 10, generation: 2)), .sameGeneration)
        let oldTap = queue.beginCapture(epoch: try XCTUnwrap(snapshots.audioGeneration))
        queue.enqueueAudio(Data([1, 0]), token: oldTap)
        queue.enqueue(ClientFrame(type: "ping"))
        transcript.update(role: "user", text: "finished", turnID: "u1", final: true)
        transcript.update(role: "user", text: "unsent", turnID: "u2", final: false)
        transcript.reconcile([])

        // The client performs this invalidation before starting the replacement tap.
        XCTAssertEqual(snapshots.accept(try snapshot(revision: 11, generation: 3)), .newGeneration)
        queue.stopCaptureAndDiscardAudio()
        transcript.discardPartialInput()
        transcript.reconcile(try snapshot(extra: """
        ,"messages":[{"role":"user","text":"unsent","turn_id":"u2","final":false}]
        """).messages)
        XCTAssertEqual(transcript.turns.map(\.text), ["finished"])
        let freshTap = queue.beginCapture(epoch: try XCTUnwrap(snapshots.audioGeneration))
        queue.enqueueAudio(Data([2, 0]), token: oldTap)
        queue.enqueueAudio(Data([3, 0]), token: freshTap)
        XCTAssertEqual(try fields(XCTUnwrap(queue.pop()).json)["type"], .string("ping"))
        XCTAssertEqual(try fields(XCTUnwrap(queue.pop()).json),
                       ["type": .string("audio"), "data": .string("AwA="), "epoch": .number(3)])
        XCTAssertNil(queue.pop())

        XCTAssertNil(snapshots.accept(try snapshot(revision: 10, generation: 4)))
        XCTAssertNil(snapshots.accept(try snapshot(revision: 12, generation: 2)))
        XCTAssertNil(snapshots.accept(try snapshot(revision: 12, generation: 4, id: "different")))
        XCTAssertFalse(snapshots.acceptHello(generation: 2))
        XCTAssertEqual(snapshots.audioGeneration, 3)
        XCTAssertTrue(snapshots.acceptHello(generation: 4))
        XCTAssertNil(snapshots.accept(try snapshot(revision: 12, generation: 3)))
    }

    func testTranscriptFinalReplacesPartialAndIgnoresDelayedUpdate() {
        var transcript = TranscriptStore()
        transcript.update(role: "user", text: "Which", turnID: "u", final: false)
        transcript.reconcile([])
        transcript.update(role: "user", text: "Which color?", turnID: "u", final: true)
        transcript.reconcile([])
        transcript.update(role: "user", text: "Which", turnID: "u", final: false)
        transcript.discardPartialInput()
        XCTAssertEqual(transcript.turns.map(\.text), ["Which color?"])
    }

    func testPlayedRequiresEndAndEveryPlaybackCallback() throws {
        var ledger = PlaybackLedger()
        ledger.begin("r1")
        let first = try XCTUnwrap(ledger.schedule("r1"))
        let second = try XCTUnwrap(ledger.schedule("r1"))
        XCTAssertNil(ledger.played(first, reply: "r1"))
        XCTAssertNil(ledger.finish("r1"))
        XCTAssertNil(ledger.schedule("r1"))
        XCTAssertNil(ledger.played(first, reply: "r1"))
        XCTAssertEqual(ledger.played(second, reply: "r1"), "r1")
        XCTAssertNil(ledger.finish("r1"))

        ledger.begin("r2")
        let early = try XCTUnwrap(ledger.schedule("r2"))
        XCTAssertNil(ledger.played(early, reply: "r2"))
        XCTAssertEqual(ledger.finish("r2"), "r2")
        ledger.begin("r3")
        let interrupted = try XCTUnwrap(ledger.schedule("r3"))
        ledger.invalidate()
        XCTAssertNil(ledger.played(interrupted, reply: "r3"))
        XCTAssertNil(ledger.finish("r3"))
        ledger.begin("empty")
        XCTAssertNil(ledger.finish("empty"))
    }

    func testMuteAndCloseRejectStaleCaptureCallbacks() throws {
        let queue = OutboundFIFO()
        let oldTap = queue.beginCapture(epoch: 1)
        queue.enqueue(ClientFrame.reply("played", id: "r1"))
        queue.enqueueAudio(Data([1, 0]), token: oldTap)
        queue.stopCaptureAndDiscardAudio()
        queue.enqueue(.mute(true))
        queue.enqueueAudio(Data([2, 0]), token: oldTap)
        queue.fail("stale conversion", token: oldTap)
        XCTAssertNil(queue.failure)
        XCTAssertEqual(try fields(XCTUnwrap(queue.pop()).json)["type"], .string("played"))
        XCTAssertEqual(try fields(XCTUnwrap(queue.pop()).json)["muted"], .bool(true))
        XCTAssertNil(queue.pop())
        queue.close()
        queue.enqueue(ClientFrame(type: "stop"))
        XCTAssertNil(queue.pop())
    }

    func testConcurrentMuteDiscardsOldTapAudio() {
        let queue = OutboundFIFO(maxFrames: 3000, maxBytes: 20_000)
        let token = queue.beginCapture(epoch: 1)
        DispatchQueue.concurrentPerform(iterations: 2000) { index in
            if index == 500 { queue.stopCaptureAndDiscardAudio() }
            queue.enqueueAudio(Data([0, 0]), token: token)
        }
        XCTAssertEqual(queue.count, 0)
        XCTAssertNil(queue.failure)
    }

    func testBoundedQueueFailsClosedAndCoalescesWakeups() async {
        for queue in [OutboundFIFO(maxFrames: 1), OutboundFIFO(maxBytes: 4)] {
            let token = queue.beginCapture(epoch: 1)
            queue.enqueueAudio(Data([0, 0]), token: token)
            queue.enqueueAudio(Data([0, 0]), token: token)
            XCTAssertNotNil(queue.failure)
            XCTAssertNil(queue.pop())
            queue.close()
            var signals = 0
            for await _ in queue.wakeups { signals += 1 }
            XCTAssertEqual(signals, 1)
        }
    }

    func testStreamedLittleEndianPCMAndMalformedChunks() throws {
        let samples: [Int16] = [0, 1, -1, .min, .max, 0x1234]
        let wire = samples.withUnsafeBufferPointer(PCMBytes.littleEndian)
        XCTAssertEqual(wire, Data([0, 0, 1, 0, 255, 255, 0, 128, 255, 127, 0x34, 0x12]))
        XCTAssertEqual(try PCMBytes.floats(wire), samples.map { Float($0) / 32768 })
        for bytes in [Data(), Data([1]), Data(repeating: 0, count: 480_002)] {
            XCTAssertThrowsError(try PCMBytes.floats(bytes))
        }
    }

    func testHeartbeatRejectsUnsolicitedAndReplayedPongs() {
        var heartbeat = Heartbeat(now: 0)
        let seq = heartbeat.ping()
        heartbeat.pong(seq + 1, now: 14)
        XCTAssertTrue(heartbeat.expired(now: 15))
        heartbeat.pong(seq, now: 16)
        XCTAssertFalse(heartbeat.expired(now: 30))
        heartbeat.pong(seq, now: 18)
        XCTAssertTrue(heartbeat.expired(now: 31))
    }

    func testOptionalRecordsPreserveIndependentProvenanceAndAssociations() throws {
        let legacy = try snapshot(state: #""ready""#)
        XCTAssertEqual(legacy.state, .string("ready"))
        XCTAssertTrue(legacy.taskRecords.isEmpty)
        XCTAssertTrue(legacy.sceneRecords.isEmpty)
        XCTAssertTrue(legacy.skillRecords.isEmpty)

        let lab = try snapshot(extra: """
        ,"task":null,"tasks":[
          {"task_id":"clarify","status":"needs_clarification","summary":"Which labeled sample?","request_id":null},
          {"task_id":"t","status":"executing","request_id":"p2","execution":[{"status":"completed","backend":"mock"}]}],
        "scene":{"fresh":false,"provenance":"recorded_simulation"},
        "scene_images":[{"evidence_id":"e1","captured_at":123,"sha256":"fixture-hash","provenance":"recorded_simulation"}],
        "outcomes":[{"status":"unknown","provenance":"UNKNOWN","evidence_ids":["e1"]}],
        "skills":[{"skill_id":"ph","version":"fixture-version","status":"task_validated"}],
        "notebook":[
          {"kind":"execution_progress","data":{"task_id":"t","request_id":"p2","phase":"prepared"}},
          {"kind":"execution_progress","data":{"task_id":"t","request_id":"p1","phase":"superseded"}},
          {"kind":"skill_evaluation","data":{"skill_id":"ph","decision":{"decision":"rejected"}}}],
        "observations":[
          {"observation_id":"o1","request_id":"p2","trial_id":"t1","provenance":"UNKNOWN","source":"observer","text":"Unreadable","evidence":[]},
          {"observation_id":"o2","request_id":"p2","trial_id":"t1","provenance":"recorded_simulation","source":"observer","text":"Observed","evidence":["e1"]}]
        """)
        let task = try XCTUnwrap(lab.taskRecords.first)
        XCTAssertEqual(task["request_id"], .null)
        XCTAssertEqual(RecordPresentation.clarification(task), "Which labeled sample?")
        XCTAssertEqual(lab.latestProgress(for: lab.taskRecords[1])?["phase"], .string("prepared"))
        XCTAssertEqual(lab.imageRecords.first?["captured_at"], .number(123))
        XCTAssertEqual(lab.sceneRecords.first?["fresh"], .bool(false))
        XCTAssertEqual(lab.executionRecords.first?["status"], .string("completed"))
        XCTAssertEqual(lab.outcomeRecords.first?["status"], .string("unknown"))
        XCTAssertEqual(lab.observations.map(\.id), ["o1", "o2"])
        XCTAssertEqual(lab.observations.map(\.provenance), ["UNKNOWN", "recorded_simulation"])
        XCTAssertEqual(lab.skillRecords.first?["status"], .string("task_validated"))
        XCTAssertEqual(lab.evaluationRecords.first?["decision"]?["decision"], .string("rejected"))
    }

    private func snapshot(revision: Int = 0, generation: Int = 0, id: String = "s",
                          state: String = #"{"at":"HOME","state_provenance":"MOCK"}"#,
                          extra: String = "") throws -> LabSnapshot {
        let base = """
        {"session_id":"\(id)","backend":"mock","revision":\(revision),"generation":\(generation),"connected":true,
        "experiment":{"id":"red_cabbage_ph","title":"Red-cabbage pH","question":"What changes?"},
        "trial":{"trial_id":"t1","state":"ready"},"conditions":[],"prediction":"",
        "observations":[],"messages":[],"notebook":[],"state":\(state)}
        """
        var fields = try self.fields(base)
        let additions = try self.fields("{\"fixture\":true\(extra)}")
        fields.merge(additions) { _, new in new }
        return try JSONDecoder().decode(LabSnapshot.self, from: JSONEncoder().encode(fields))
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(type, from: Data(json.utf8))
    }

    private func fields(_ json: String) throws -> [String: JSONValue] {
        try decode([String: JSONValue].self, json)
    }
}
