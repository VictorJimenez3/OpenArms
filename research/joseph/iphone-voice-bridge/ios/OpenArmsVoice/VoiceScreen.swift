import SwiftUI
import UIKit

private enum LabStyle {
    static let background = color(0xfbfdfc)
    static let subtle = color(0xf7f9f8)
    static let line = color(0xdfe4e2)
    static let ink = color(0x1a211e)
    static let muted = color(0x5f6563)
    static let jade = color(0x208368)
    static let stop = color(0xb42318)

    private static func color(_ rgb: UInt32) -> Color {
        Color(red: Double((rgb >> 16) & 255) / 255,
              green: Double((rgb >> 8) & 255) / 255,
              blue: Double(rgb & 255) / 255)
    }
}

struct VoiceScreen: View {
    @StateObject private var client = VoiceClient()
    @AppStorage("phServerOrigin") private var address = ""
    @AppStorage("phLocalDevelopment") private var localDevelopment = false
    @Environment(\.scenePhase) private var scenePhase
    @State private var sheet: Panel?
    @State private var sheetIsVisible = false
    @State private var prediction = ""
    @State private var reflection = ""
    @State private var message = ""
    @FocusState private var focusedField: Field?

    private enum Field { case prediction, reflection, message }
    private enum Panel: String, Identifiable {
        case type, history, settings
        var id: Self { self }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(LabStyle.line)
            ScrollViewReader { scroll in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        camera
                        voiceControl
                        if let proposal = client.snapshot?.pending, client.connected {
                            proposalCard(proposal)
                        }
                        clarification
                        if let notice = client.notice { noticeCard(notice) }
                        secondaryActions
                    }
                    .padding(.horizontal, 20).padding(.vertical, 16)
                    .frame(maxWidth: 560).frame(maxWidth: .infinity)
                }
                .onChange(of: reviewableProposalID, initial: true) { _, id in
                    if let id { scroll.scrollTo(id, anchor: .top) }
                }
            }
        }
        .background(LabStyle.background.ignoresSafeArea())
        .tint(LabStyle.jade).foregroundStyle(LabStyle.ink).preferredColorScheme(.light)
        .sheet(item: $sheet, onDismiss: { sheetIsVisible = false }) { panel in
            switch panel {
            case .type:
                detailSheet("Type instead") {
                    clarification
                    requestComposer
                    if let notice = client.notice { noticeCard(notice) }
                }
            case .history:
                detailSheet("History") { historyContent }
            case .settings:
                ConnectionSettings(client: client, address: $address, localDevelopment: $localDevelopment)
            }
        }
        .task {
            if !address.isEmpty { client.connect(address: address, allowLocalDebug: debugLocalAllowed) }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { client.setForeground(false) }
            if phase == .active { client.setForeground(true) }
        }
        .onChange(of: client.connectionStatus) { _, status in
            UIAccessibility.post(notification: .announcement, argument: status)
        }
        .onChange(of: client.snapshot?.trial.trialID) { _, _ in prediction = ""; reflection = "" }
        .onChange(of: connectedProposalID) { _, id in
            if id != nil { sheet = nil }
        }
    }

    private var debugLocalAllowed: Bool {
        #if DEBUG
        localDevelopment
        #else
        false
        #endif
    }

    private func open(_ panel: Panel) {
        sheetIsVisible = true
        sheet = panel
    }

    private var reviewableProposalID: String? {
        sheetIsVisible ? nil : connectedProposalID
    }

    private var connectedProposalID: String? {
        client.connected ? client.snapshot?.pending?.id : nil
    }

    private var header: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) {
                appTitle
                Spacer(minLength: 0)
                connectionIndicator
                stopButton(client) { focusedField = nil }
            }
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    appTitle
                    Spacer()
                    stopButton(client) { focusedField = nil }
                }
                connectionIndicator
            }
        }
        .padding(.horizontal, 20).padding(.vertical, 4)
        .frame(maxWidth: 560).frame(maxWidth: .infinity)
    }

    private var appTitle: some View {
        Text("OpenArms").font(.title2.weight(.semibold))
            .accessibilityAddTraits(.isHeader)
    }

    private var connectionIndicator: some View {
        HStack(spacing: 6) {
            Image(systemName: client.connected ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(client.connected ? LabStyle.jade : LabStyle.muted)
                .accessibilityHidden(true)
            Text(client.connected ? "Connected" : (client.connecting ? "Connecting" : "Offline"))
                .foregroundStyle(LabStyle.muted)
        }
        .font(.subheadline)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(client.connectionStatus)
        .accessibilityIdentifier("connectionState")
    }

    private var camera: some View {
        let lab = client.snapshot
        let frame = lab?.imageRecords.last
        let simulationFrame = lab?.simulationFrame
        let showingSimulation = simulationFrame != nil &&
            (frame == nil || lab?.simulationStatus == "running")

        return VStack(spacing: 0) {
            Group {
                if showingSimulation, let simulationFrame {
                    EvidenceImage(client: client, id: simulationFrame.id, path: simulationFrame.path,
                                  scope: client.evidenceScope, maxHeight: 246, label: "MuJoCo simulation frame")
                } else if let frame {
                    sceneImage(frame, maxHeight: 246)
                } else {
                    Label(client.connected ? "Waiting for a scene image" : "Camera offline",
                          systemImage: "camera")
                        .font(.subheadline).foregroundStyle(LabStyle.muted)
                }
            }
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
            .frame(height: 246)
            if showingSimulation {
                cameraCaption("MuJoCo simulation frame")
            } else if let frame {
                cameraCaption(RecordPresentation.provenance(frame), time: captureTime(frame))
            }
        }
        .background(LabStyle.subtle, in: RoundedRectangle(cornerRadius: 16))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(LabStyle.line))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Lab camera")
    }

    private func cameraCaption(_ source: String, time: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(source).font(.caption.weight(.semibold))
            if let time { Text(time).font(.caption2) }
        }
        .foregroundStyle(LabStyle.muted)
        .padding(.horizontal, 14).padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .top) { Divider().overlay(LabStyle.line) }
    }

    @ViewBuilder
    private var clarification: some View {
        if client.connected, let latest = client.snapshot?.taskRecords.last,
           let question = RecordPresentation.clarification(latest) {
            VStack(alignment: .leading, spacing: 6) {
                Text("OpenArms asks").font(.subheadline.weight(.semibold))
                Text(question).textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16).card()
        }
    }

    private var activityStatus: String {
        guard client.connected else { return address.isEmpty ? "Lab disconnected" : client.connectionStatus }
        switch client.snapshot?.simulationStatus {
        case "failed": return "Simulation failed"
        case "unavailable": return "Simulation unavailable"
        default: break
        }
        if client.speakerActive { return "Speaking" }
        if client.voiceWanted && client.muted { return "Microphone muted" }
        if client.voiceWanted && client.voiceStatus == "paused" { return "Voice paused" }
        switch client.snapshot?.taskRecords.last?["status"]?.string {
        case "queued": return "Request queued"
        case "running": return "Preparing your task"
        case "executing": return "Running the approved plan"
        case "observing": return "Checking the result"
        case "needs_clarification": return "Waiting for your answer"
        case "failed": return "Task failed"
        case "cancelled" where client.snapshot?.trial.state != "stopped": return "Task cancelled"
        default: break
        }
        if client.snapshot?.pending != nil { return "Review the proposed action" }
        if client.voiceStatus == "unavailable" { return "Voice unavailable" }
        if client.microphoneActive { return "Listening" }
        if client.voiceWanted {
            return client.voiceStatus == "reconnecting" ? "Reconnecting voice" : "Connecting voice"
        }
        if client.snapshot?.trial.state == "stopped", !client.busy { return "Lab stopped" }
        if client.busy { return "Sending to the lab" }
        return "Ready"
    }

    private var voiceControl: some View {
        VStack(spacing: 10) {
            Text(activityStatus).font(.subheadline.weight(.medium))
                .foregroundStyle(LabStyle.muted).multilineTextAlignment(.center)
                .accessibilityIdentifier("labActivity")
            Button {
                focusedField = nil
                if client.voiceWanted { client.stopVoice() }
                else if client.connected { client.toggleVoice() }
                else { open(.settings) }
            } label: {
                Label(voiceAction.title, systemImage: voiceAction.icon)
                    .font(.title3.weight(.semibold))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16).padding(.vertical, 18)
                    .frame(maxWidth: .infinity, minHeight: 68)
            }
            .buttonStyle(.borderedProminent)
            .buttonBorderShape(.roundedRectangle(radius: 16))
            .disabled(client.connecting && !client.voiceWanted)
            .accessibilityIdentifier("primaryVoice")
        }
    }

    private var voiceAction: (title: String, icon: String) {
        if client.voiceWanted { return ("End voice", "mic.slash.fill") }
        if client.connected || client.connecting { return ("Talk", "mic.fill") }
        return ("Connect to lab", "link")
    }

    private var secondaryActions: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 18) {
                typeButton
                historyButton
                settingsButton
            }
            VStack(spacing: 0) {
                typeButton
                historyButton
                settingsButton
            }
        }
        .font(.subheadline.weight(.medium))
        .foregroundStyle(LabStyle.jade)
        .frame(maxWidth: .infinity)
    }

    private var typeButton: some View {
        Button { open(.type) } label: { Text("Type instead").frame(minHeight: 44) }
    }

    private var historyButton: some View {
        Button { open(.history) } label: { Text("History").frame(minHeight: 44) }
    }

    private var settingsButton: some View {
        Button { open(.settings) } label: { Text("Settings").frame(minHeight: 44) }
            .accessibilityIdentifier("connectionSettings")
    }

    private func detailSheet<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16, content: content)
                    .padding(20).frame(maxWidth: 560).frame(maxWidth: .infinity)
            }
            .background(LabStyle.background.ignoresSafeArea())
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { sheet = nil } }
                ToolbarItem(placement: .topBarTrailing) {
                    stopButton(client) { focusedField = nil; sheet = nil }
                }
            }
        }
    }

    @ViewBuilder
    private var historyContent: some View {
        if !client.messages.isEmpty { conversation }
        if let lab = client.snapshot {
            if !lab.taskRecords.isEmpty { taskUpdates(lab) }
            if !lab.observations.isEmpty { evidence(lab) }
            if !lab.outcomeRecords.isEmpty { outcomes(lab) }
            if !lab.sceneRecords.isEmpty || !lab.imageRecords.isEmpty { sceneEvidence(lab) }
            if !lab.executionRecords.isEmpty { execution(lab) }
            if lab.experiment.id == "indicator_ph" { trial(lab) }
            if !lab.skillRecords.isEmpty || !lab.evaluationRecords.isEmpty { skills(lab) }
            history(lab)
        } else if client.messages.isEmpty {
            Text("Your conversation and trial evidence will appear here.")
                .foregroundStyle(LabStyle.muted)
        }
    }

    private func trial(_ lab: LabSnapshot) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 18) {
                Text(lab.experiment.question).font(.body)
                Text("Prepared conditions").font(.subheadline.weight(.semibold))
                // A vertical group preserves readable labels at large accessibility text sizes.
                VStack(spacing: 10) {
                    ForEach(lab.conditions) { condition in
                        let selected = condition.id == lab.trial.conditionID
                        Button { client.chooseCondition(condition.id) } label: {
                            HStack(spacing: 12) {
                                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                                Text(condition.title).font(.body.weight(selected ? .semibold : .regular))
                                Spacer(minLength: 0)
                            }
                            .padding(.horizontal, 16).frame(maxWidth: .infinity, minHeight: 52)
                            .background(selected ? LabStyle.jade.opacity(0.11) : Color.white.opacity(0.75), in: RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(selected ? LabStyle.jade : .clear, lineWidth: 1.5))
                        }
                        .buttonStyle(.plain).disabled(!client.canAct)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                        .accessibilityIdentifier("condition_\(condition.id)")
                    }
                }
                Text("Prediction").font(.subheadline.weight(.semibold))
                if !lab.prediction.isEmpty {
                    Label(lab.prediction, systemImage: "quote.bubble").font(.subheadline).foregroundStyle(LabStyle.jade).textSelection(.enabled)
                }
                TextField("What color or classification do you expect?", text: $prediction, axis: .vertical)
                    .lineLimit(2...5).padding(14).background(.white, in: RoundedRectangle(cornerRadius: 14))
                    .focused($focusedField, equals: .prediction).accessibilityLabel("Your prediction")
                Button(lab.prediction.isEmpty ? "Save prediction" : "Update prediction") {
                    client.predict(prediction); focusedField = nil
                }
                .buttonStyle(.bordered).frame(minHeight: 44)
                .disabled(!client.canAct || prediction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Start another trial") { client.prepare(); focusedField = nil }
                    .buttonStyle(.bordered).frame(minHeight: 44).disabled(!client.canAct || lab.pending != nil)
            }.padding(.top, 10)
        } label: {
            Label("Optional trial context", systemImage: "flask").font(.headline).frame(minHeight: 44)
        }.padding(22).card()
    }

    private func proposalCard(_ proposal: Proposal) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Proposed action").font(.headline).accessibilityAddTraits(.isHeader)
            if let summary = proposal.reviewSummary {
                Text(summary).font(.body).textSelection(.enabled)
            } else {
                Text("No preview is available. Ask for a fresh plan.")
                    .font(.body).foregroundStyle(LabStyle.muted)
            }
            TimelineView(.periodic(from: .now, by: 1)) { context in
                let expired = (proposal.expiresAt ?? .infinity) <= context.date.timeIntervalSince1970
                VStack(spacing: 8) {
                    Button { focusedField = nil; client.confirm(proposal) } label: {
                        Text("Confirm plan").font(.headline).frame(maxWidth: .infinity, minHeight: 50)
                    }
                    .buttonStyle(.borderedProminent).disabled(expired || !client.canConfirm)
                    .accessibilityIdentifier("confirmProposal")
                    if expired {
                        Text("Proposal expired. Ask for a new plan.")
                            .font(.caption).foregroundStyle(LabStyle.muted)
                    } else if !client.canConfirm && !client.busy {
                        Text("Waiting for the lab to acknowledge this preview.")
                            .font(.caption).foregroundStyle(LabStyle.muted)
                    }
                }
            }
            Button("Cancel proposal", role: .destructive) { client.cancel(proposal) }
                .frame(maxWidth: .infinity, minHeight: 44).disabled(!client.canAct)
        }
        .padding(22).background(LabStyle.jade.opacity(0.08), in: RoundedRectangle(cornerRadius: 24))
        .id(proposal.id)
        .task(id: reviewableProposalID) {
            if reviewableProposalID == proposal.id, proposal.reviewSummary != nil {
                client.proposalAppeared(proposal)
            } else {
                client.proposalDisappeared(proposal.id)
            }
        }
        .onDisappear { client.proposalDisappeared(proposal.id) }
        .accessibilityElement(children: .contain)
    }

    private func taskUpdates(_ lab: LabSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Task progress").font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(Array(lab.taskRecords.suffix(3).enumerated()), id: \.offset) { _, task in
                VStack(alignment: .leading, spacing: 6) {
                    let status = task["status"]?.string
                    if ["queued", "running"].contains(status) {
                        ProgressView(status == "queued" ? "Request received" : "Preparing your task").controlSize(.small)
                    } else if let status = RecordPresentation.status(task) {
                        Text(status.capitalized).font(.subheadline.bold())
                    }
                    if let request = RecordPresentation.text(task, "request", "goal") { Text(request) }
                    if let question = RecordPresentation.clarification(task) {
                        Text(question).fontWeight(.medium)
                        Text("Reply by voice or type your answer.").font(.footnote).foregroundStyle(.secondary)
                    } else if let summary = RecordPresentation.text(task, "summary", "reason") {
                        Text(summary)
                    }
                    if let progress = lab.latestProgress(for: task) {
                        metadata("Current operation", RecordPresentation.text(progress, "operation")?.replacingOccurrences(of: "_", with: " "))
                        metadata("Phase", RecordPresentation.text(progress, "phase"))
                    }
                    if task["route"]?.string == "active_skill" {
                        Label("Used a saved skill", systemImage: "bolt").font(.footnote)
                    }
                    if let metrics = lab.metrics(for: task) {
                        if let milliseconds = metrics["planning_ms"]?.numericValue {
                            metadata("Planning", "\(milliseconds.formatted(.number.precision(.fractionLength(0)))) ms")
                        }
                        metadata("Model calls", RecordPresentation.text(metrics, "model_calls"))
                    }
                    if let id = task["task_id"]?.string,
                       ["queued", "running", "awaiting_confirmation", "executing", "observing"].contains(status) {
                        Button("Cancel task", role: .destructive) { client.cancelTask(id) }
                            .buttonStyle(.bordered).frame(minHeight: 44).disabled(!client.canAct)
                    }
                }
            }
        }.padding(22).card()
    }

    private func sceneEvidence(_ lab: LabSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Scene evidence", systemImage: "photo.on.rectangle").font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(Array(lab.imageRecords.suffix(4).enumerated()), id: \.offset) { _, frame in
                evidenceFrame(frame)
            }
            if !lab.sceneRecords.isEmpty {
                DisclosureGroup("Scene details") {
                    ForEach(Array(lab.sceneRecords.suffix(4).enumerated()), id: \.offset) { _, record in
                        evidenceMetadata(record).padding(.top, 8)
                    }
                }
            }
        }.padding(20).card()
    }

    private func evidenceFrame(_ frame: JSONValue) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            sceneImage(frame)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            evidenceMetadata(frame)
        }
    }

    @ViewBuilder
    private func sceneImage(_ frame: JSONValue, maxHeight: CGFloat = 260) -> some View {
        if let id = frame["evidence_id"]?.string, let path = frame["artifact_url"]?.string {
            EvidenceImage(client: client, id: id, path: path, scope: client.evidenceScope, maxHeight: maxHeight)
        } else {
            Text("Scene image unavailable").font(.footnote).foregroundStyle(LabStyle.muted)
        }
    }

    private func evidenceMetadata(_ record: JSONValue) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            if let title = RecordPresentation.text(record, "description", "summary", "text") { Text(title) }
            Text(RecordPresentation.provenance(record)).font(.caption.bold()).foregroundStyle(LabStyle.jade)
            metadata("Captured", captureTime(record))
            metadata("Clock", RecordPresentation.text(record, "capture_clock", "clock"))
            metadata("Camera", RecordPresentation.text(record, "camera_id"))
            if case let .bool(fresh) = record["fresh"] { metadata("Freshness", fresh ? "Fresh" : "Stale") }
            metadata("Coordinate frame", RecordPresentation.text(record, "coordinate_frame"))
            metadata("Uncertainty", RecordPresentation.text(record, "uncertainty"))
            let labels = RecordPresentation.strings(record["verified_labels"])
            if !labels.isEmpty { metadata("Verified labels", labels.joined(separator: ", ")) }
            ForEach(Array(RecordPresentation.records(record["detections"]).suffix(8).enumerated()), id: \.offset) { _, detection in
                metadata("Detection", RecordPresentation.text(detection, "label", "class_name"))
                metadata("Method", RecordPresentation.text(detection, "method", "model_version", "model"))
                metadata("Uncertainty", RecordPresentation.text(detection, "uncertainty"))
            }
        }
    }

    private func captureTime(_ record: JSONValue) -> String? {
        let timestamp = record["captured_at"] ?? record["capture_timestamp"]
        if let seconds = timestamp?.numericValue, seconds.isFinite, (0...253402300799).contains(seconds) {
            return Date(timeIntervalSince1970: seconds).formatted(date: .abbreviated, time: .standard)
        }
        return timestamp?.scalarText
    }

    private func execution(_ lab: LabSnapshot) -> some View {
        DisclosureGroup {
            ForEach(Array(lab.executionRecords.suffix(4).enumerated()), id: \.offset) { _, receipt in
                VStack(alignment: .leading, spacing: 5) {
                    metadata("Controller status", RecordPresentation.status(receipt))
                    metadata("Backend", RecordPresentation.text(receipt, "backend"))
                    metadata("Details", RecordPresentation.text(receipt, "summary", "reason", "text"))
                }.padding(.top, 8)
            }
        } label: { Label("Execution receipts", systemImage: "list.bullet.clipboard").font(.headline).frame(minHeight: 44) }
        .padding(20).card()
    }

    private func outcomes(_ lab: LabSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Outcomes").font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(Array(lab.outcomeRecords.suffix(4).enumerated()), id: \.offset) { _, outcome in
                evidenceMetadata(outcome)
                metadata("Observer status", RecordPresentation.status(outcome))
            }
        }.padding(20).card()
    }

    private func skills(_ lab: LabSnapshot) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(lab.skillRecords.suffix(8).enumerated()), id: \.offset) { _, skill in
                    VStack(alignment: .leading, spacing: 4) {
                        if let name = RecordPresentation.text(skill, "name", "title", "intent") { Text(name).fontWeight(.medium) }
                        metadata("Status", RecordPresentation.status(skill))
                    }
                }
                ForEach(Array(lab.evaluationRecords.suffix(4).enumerated()), id: \.offset) { _, evaluation in
                    let decision = evaluation["decision"] ?? evaluation
                    metadata("Decision", RecordPresentation.text(decision, "decision", "status", "outcome"))
                    let receipt = evaluation["receipt"] ?? evaluation
                    metadata("Baseline cases recovered", RecordPresentation.text(receipt, "baseline_recovered"))
                    metadata("Candidate cases recovered", RecordPresentation.text(receipt, "candidate_recovered"))
                    let reasons = RecordPresentation.strings(receipt["reasons"])
                    if !reasons.isEmpty { metadata("Reasons", reasons.joined(separator: " ")) }
                }
            }.padding(.top, 10).frame(maxWidth: .infinity, alignment: .leading)
        } label: { Label("Reusable skills", systemImage: "books.vertical").font(.headline).frame(minHeight: 44) }
        .padding(20).card()
    }

    @ViewBuilder
    private func metadata(_ label: String, _ value: String?) -> some View {
        if let value {
            Text("\(label) · \(value)").font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
        }
    }

    private func evidence(_ lab: LabSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("Independent observations", systemImage: "sparkle.magnifyingglass").font(.title2.weight(.semibold)).accessibilityAddTraits(.isHeader)
            ForEach(lab.observations.suffix(3)) { observation in
                VStack(alignment: .leading, spacing: 8) {
                    Text(observation.provenance)
                        .font(.caption.bold()).foregroundStyle(LabStyle.jade)
                    Text(observation.text).textSelection(.enabled)
                    metadata("Source", observation.source)
                    if let status = observation.status { metadata("Observer status", status.capitalized) }
                    if observation.checks?.failedChecks == true { metadata("Outcome checks", "One or more checks failed") }
                    ForEach(Array(observation.images.suffix(2).enumerated()), id: \.offset) { _, frame in
                        evidenceFrame(frame)
                    }
                }.padding(.vertical, 4)
            }
            if lab.experiment.id == "indicator_ph", ["reflecting", "complete", "stopped"].contains(lab.trial.state),
               lab.observations.contains(where: { $0.trialID == lab.trial.trialID }) {
                Divider()
                DisclosureGroup("Optional reflection") {
                    TextField("What did you notice?", text: $reflection, axis: .vertical)
                        .lineLimit(2...6).padding(14).background(.white, in: RoundedRectangle(cornerRadius: 14))
                        .focused($focusedField, equals: .reflection).accessibilityLabel("Your reflection")
                    Button("Save reflection") { client.reflect(reflection); reflection = ""; focusedField = nil }
                        .buttonStyle(.bordered).frame(minHeight: 44)
                        .disabled(!client.canAct || reflection.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }.padding(22).card()
    }

    private var requestComposer: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField("Ask a question or request an action", text: $message, axis: .vertical)
                .lineLimit(2...5).padding(14).background(.white, in: RoundedRectangle(cornerRadius: 14))
                .focused($focusedField, equals: .message).accessibilityLabel("Message OpenArms")
            Button {
                if client.sendText(message) { message = ""; focusedField = nil; sheet = nil }
            } label: {
                Label("Send message", systemImage: "arrow.up.circle").frame(minHeight: 44)
            }.buttonStyle(.bordered)
                .disabled(!client.canAct || DirectLabRequest.cleanedText(message) == nil)
            if message.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.count > 4000 {
                Text("Keep the message to 4,000 characters or fewer.").font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    private var conversation: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Conversation").font(.title2.weight(.semibold)).accessibilityAddTraits(.isHeader)
            ForEach(client.messages.suffix(10)) { entry in
                VStack(alignment: .leading, spacing: 5) {
                    Text(entry.role == "user" ? "You" : "OpenArms").font(.caption.bold()).foregroundStyle(.secondary)
                    Text(entry.text).font(.body).textSelection(.enabled)
                }
                .padding(16).frame(maxWidth: .infinity, alignment: .leading)
                .background(entry.role == "user" ? LabStyle.jade.opacity(0.08) : Color.white.opacity(0.8), in: RoundedRectangle(cornerRadius: 18))
                .accessibilityElement(children: .combine)
            }
        }
    }

    private func history(_ lab: LabSnapshot) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 16) {
                if lab.notebook.isEmpty { Text("Your saved reflections and trials will appear here.").foregroundStyle(.secondary) }
                ForEach(Array(lab.notebook.enumerated()), id: \.offset) { _, entry in
                    // Show human prose from the canonical notebook; never developer JSON.
                    let data = entry["data"] ?? entry
                    let text = RecordPresentation.text(data, "text", "reflection", "summary")
                    if let text, !text.isEmpty { Text(text).font(.subheadline).textSelection(.enabled) }
                }
                ForEach(lab.observations) { observation in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(observation.provenance)
                            .font(.caption.bold()).foregroundStyle(LabStyle.jade)
                        Text(observation.text).font(.subheadline)
                    }
                }
            }.padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)
        } label: { Label("Trial notebook", systemImage: "book.closed").font(.headline).frame(minHeight: 44) }
        .padding(20).card()
    }

    private func noticeCard(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(text).font(.subheadline)
            if client.needsMicrophoneSettings {
                Button("Open microphone settings") { openSettings() }.frame(minHeight: 44)
            }
        }.padding(18).background(Color.white.opacity(0.8), in: RoundedRectangle(cornerRadius: 18))
        .accessibilityElement(children: .contain)
    }
}

private struct EvidenceImage: View {
    @ObservedObject var client: VoiceClient
    let id: String
    let path: String
    let scope: VoiceClient.EvidenceScope?
    let maxHeight: CGFloat
    var label = "Captured scene image"

    private struct LoadKey: Hashable {
        let id: String
        let path: String
        let scope: VoiceClient.EvidenceScope
    }

    private enum Result {
        case image(UIImage)
        case unavailable
    }

    @State private var loaded: (key: LoadKey, result: Result)?
    private var key: LoadKey? { scope.map { LoadKey(id: id, path: path, scope: $0) } }

    var body: some View {
        Group {
            if let key {
                if let loaded, loaded.key == key {
                    switch loaded.result {
                    case let .image(image):
                        Image(uiImage: image).resizable().scaledToFit()
                            .frame(maxWidth: .infinity, maxHeight: maxHeight)
                            .accessibilityLabel(label)
                    case .unavailable:
                        Text("Scene image unavailable").font(.footnote).foregroundStyle(.secondary)
                    }
                } else {
                    ProgressView("Loading scene image").controlSize(.small)
                }
            } else {
                Text("Camera offline").font(.footnote).foregroundStyle(.secondary)
            }
        }
        .task(id: key) { [key] in
            loaded = nil
            guard let key else { return }
            do {
                let image = try await client.loadEvidenceImage(id: key.id, path: key.path, scope: key.scope)
                try Task.checkCancellation()
                guard client.evidenceScope == key.scope else { return }
                loaded = (key, .image(image))
            } catch {
                guard !Task.isCancelled, client.evidenceScope == key.scope else { return }
                loaded = (key, .unavailable)
            }
        }
    }
}

private extension View {
    func card() -> some View { background(LabStyle.subtle, in: RoundedRectangle(cornerRadius: 16)) }
}

private struct ConnectionSettings: View {
    @ObservedObject var client: VoiceClient
    @Binding var address: String
    @Binding var localDevelopment: Bool
    @State private var pairingCode = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                Section("Your lab server") {
                    TextField("https://lab.example.org", text: $address)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityLabel("HTTPS lab server address")
                    SecureField("Pairing code, if required", text: $pairingCode)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityLabel("Private demo pairing code")
                    if let notice = client.notice {
                        Text(notice).font(.footnote).foregroundStyle(LabStyle.muted)
                    }
                    Text(client.connectionStatus).font(.footnote).foregroundStyle(LabStyle.muted)
                    Button(client.connecting ? "Reconnect" : "Connect to lab") {
                        #if DEBUG
                        client.connect(address: address, pairingToken: pairingCode, allowLocalDebug: localDevelopment)
                        #else
                        client.connect(address: address, pairingToken: pairingCode)
                        #endif
                        pairingCode = ""; dismiss()
                    }.frame(minHeight: 44)
                    if client.connected {
                        Button("Disconnect and save lab", role: .destructive) { client.disconnect(); dismiss() }.frame(minHeight: 44)
                    }
                }
                #if DEBUG
                Section("Local development only") {
                    Toggle("Allow local HTTP development server", isOn: $localDevelopment)
                    Text("Only localhost, .local and private IPv4 LAN addresses are accepted. Local HTTP is unencrypted. Use trusted HTTPS for a demo. iOS may require a .local hostname for its local networking exception.")
                }
                #endif
                Section("Audio") {
                    if client.voiceWanted {
                        Button(client.muted ? "Unmute microphone" : "Mute microphone") { client.toggleMute() }
                            .frame(minHeight: 44).accessibilityIdentifier("toggleMute")
                        Button("Interrupt playback") { client.interrupt() }
                            .frame(minHeight: 44).disabled(!client.speakerActive)
                    }
                    Button("Open app settings") { openSettings() }.frame(minHeight: 44)
                }
            }
            .navigationTitle("Lab connection").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { pairingCode = ""; dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    stopButton(client) { pairingCode = ""; dismiss() }
                }
            }
        }.tint(LabStyle.jade)
    }
}
@MainActor
private func stopButton(_ client: VoiceClient, dismiss: @escaping () -> Void) -> some View {
    Button(role: .destructive) {
        dismiss()
        client.stopLab()
    } label: {
        Label("Stop", systemImage: "stop.fill")
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(LabStyle.stop)
            .frame(minWidth: 60, minHeight: 44)
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("stopLab")
    .accessibilityHint("Sends a stop command directly to the lab.")
}

@MainActor private func openSettings() {
    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
}
