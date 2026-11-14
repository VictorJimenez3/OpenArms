import SwiftUI
import UIKit

private enum LabStyle {
    static let cream = Color(red: 0.97, green: 0.96, blue: 0.92)
    static let ink = Color(red: 0.17, green: 0.16, blue: 0.22)
    static let purple = Color(red: 0.39, green: 0.25, blue: 0.49)
    static let teal = Color(red: 0.17, green: 0.39, blue: 0.36)
}

struct VoiceScreen: View {
    @StateObject private var client = VoiceClient()
    @AppStorage("phServerOrigin") private var address = ""
    @AppStorage("phLocalDevelopment") private var localDevelopment = false
    @Environment(\.scenePhase) private var scenePhase
    @State private var showConnection = false
    @State private var prediction = ""
    @State private var reflection = ""
    @State private var message = ""
    @State private var showHistory = false
    @FocusState private var focusedField: Field?
    private enum Field { case prediction, reflection, message }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    introduction
                    voiceControl
                    if let notice = client.notice { noticeCard(notice) }
                    if let lab = client.snapshot {
                        requestComposer
                        if !lab.taskRecords.isEmpty { taskUpdates(lab) }
                        if let proposal = lab.pending { proposalCard(proposal) }
                        if !lab.observations.isEmpty { evidence(lab) }
                        if !lab.outcomeRecords.isEmpty { outcomes(lab) }
                        if !lab.sceneRecords.isEmpty || !lab.imageRecords.isEmpty { sceneEvidence(lab) }
                        if !lab.executionRecords.isEmpty { execution(lab) }
                        if !client.messages.isEmpty { conversation }
                        if lab.experiment.id == "red_cabbage_ph" { trial(lab) }
                        if !lab.skillRecords.isEmpty || !lab.evaluationRecords.isEmpty { skills(lab) }
                        history(lab)
                    } else {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Connect to get started").font(.title2.weight(.semibold))
                            Text("Talk or type a question, request an experiment, and review the evidence. You can start with the red-cabbage pH demonstration.")
                                .foregroundStyle(.secondary)
                            Button(client.connecting ? "Opening your lab…" : "Connect your lab") { showConnection = true }
                                .buttonStyle(.bordered).frame(minHeight: 48).disabled(client.connecting)
                        }.padding(22).card()
                    }
                    if client.snapshot != nil {
                        Button(role: .destructive) { focusedField = nil; client.stopLab() } label: {
                            Label("Stop lab", systemImage: "stop.circle").frame(maxWidth: .infinity, minHeight: 48)
                        }
                        .buttonStyle(.bordered)
                        .accessibilityHint("Stops the lab directly, even when voice is unavailable.")
                    }
                    Text("Software demo · physical actuation disabled in this session")
                        .font(.footnote).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .center)
                }
                .padding(.horizontal, 22).padding(.vertical, 24)
                .frame(maxWidth: 640).frame(maxWidth: .infinity)
            }
            .background(LabStyle.cream.ignoresSafeArea())
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("OpenArms")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showConnection = true } label: { Label("Lab connection", systemImage: "antenna.radiowaves.left.and.right") }
                        .frame(minWidth: 44, minHeight: 44).accessibilityIdentifier("connectionSettings")
                }
                ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { focusedField = nil } }
            }
            .sheet(isPresented: $showConnection) {
                ConnectionSettings(client: client, address: $address, localDevelopment: $localDevelopment)
            }
        }
        .tint(LabStyle.purple).foregroundStyle(LabStyle.ink).preferredColorScheme(.light)
        .task {
            if !address.isEmpty { client.connect(address: address, allowLocalDebug: debugLocalAllowed) }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { client.setForeground(false) }
            if phase == .active { client.setForeground(true) }
        }
        .onChange(of: client.connectionStatus) { _, status in UIAccessibility.post(notification: .announcement, argument: status) }
        .onChange(of: client.snapshot?.trial.trialID) { _, _ in prediction = ""; reflection = "" }
    }

    private var debugLocalAllowed: Bool {
        #if DEBUG
        localDevelopment
        #else
        false
        #endif
    }

    private var introduction: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "bubble.left.and.bubble.right.fill").foregroundStyle(LabStyle.teal)
                Text("OPENARMS LAB").font(.caption.weight(.bold)).tracking(1.4)
                Spacer()
                if let backend = client.snapshot?.backend {
                    Text(backend.uppercased()).font(.caption2.bold()).padding(.horizontal, 9).padding(.vertical, 6)
                        .background(LabStyle.purple.opacity(0.10), in: Capsule())
                }
            }
            Text(client.snapshot?.experiment.title ?? "Talk with OpenArms")
                .font(.system(.largeTitle, design: .serif, weight: .medium)).accessibilityAddTraits(.isHeader)
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: client.connected ? "checkmark.circle.fill" : "circle.dotted")
                    .foregroundStyle(client.connected ? LabStyle.teal : LabStyle.purple)
                Text(client.connectionStatus).font(.footnote)
                if client.connecting { ProgressView().controlSize(.small).accessibilityLabel("Connecting") }
            }.accessibilityElement(children: .combine).accessibilityIdentifier("connectionState")
        }
    }

    private var voiceControl: some View {
        VStack(spacing: 16) {
            Button {
                focusedField = nil
                if client.connected { client.toggleVoice() } else { showConnection = true }
            } label: {
                VStack(spacing: 12) {
                    Image(systemName: client.speakerActive ? "waveform" : (client.muted ? "mic.slash.fill" : "mic.fill"))
                        .font(.system(size: 30, weight: .medium)).frame(height: 38).accessibilityHidden(true)
                    Text(client.voiceTitle).font(.headline).multilineTextAlignment(.center)
                }
                .foregroundStyle(.white).padding(24).frame(maxWidth: .infinity, minHeight: 132)
                .background(LabStyle.purple, in: RoundedRectangle(cornerRadius: 28))
            }
            .buttonStyle(.plain).accessibilityIdentifier("primaryVoice")
            .accessibilityHint(client.voiceWanted ? "Pauses voice. Your text session stays connected." : "Enables a continuous voice conversation after microphone permission.")
            Text(client.voiceDetail).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            if client.voiceWanted {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 12) { muteButton; interruptButton }
                    VStack(spacing: 8) { muteButton; interruptButton }
                }
            }
            HStack(spacing: 18) {
                Label(client.microphoneActive ? "Mic on" : "Mic off", systemImage: client.microphoneActive ? "mic" : "mic.slash")
                Label(client.speakerActive ? "Playing" : "Speaker ready", systemImage: client.speakerActive ? "speaker.wave.2" : "speaker")
            }.font(.caption).foregroundStyle(.secondary).accessibilityElement(children: .combine)
        }
    }
    private var muteButton: some View {
        Button { client.toggleMute() } label: {
            Label(client.muted ? "Unmute" : "Mute", systemImage: client.muted ? "mic.fill" : "mic.slash")
                .frame(maxWidth: .infinity, minHeight: 44)
        }.buttonStyle(.bordered).accessibilityIdentifier("toggleMute")
    }
    private var interruptButton: some View {
        Button { client.interrupt() } label: {
            Label("Interrupt", systemImage: "hand.raised").frame(maxWidth: .infinity, minHeight: 44)
        }.buttonStyle(.bordered).disabled(!client.speakerActive)
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
                            .background(selected ? LabStyle.purple.opacity(0.11) : Color.white.opacity(0.75), in: RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(selected ? LabStyle.purple : .clear, lineWidth: 1.5))
                        }
                        .buttonStyle(.plain).disabled(!client.canAct)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                        .accessibilityIdentifier("condition_\(condition.id)")
                    }
                }
                Text("Prediction").font(.subheadline.weight(.semibold))
                if !lab.prediction.isEmpty {
                    Label(lab.prediction, systemImage: "quote.bubble").font(.subheadline).foregroundStyle(LabStyle.purple).textSelection(.enabled)
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
            Label("Review before we begin", systemImage: "checkmark.shield").font(.headline).accessibilityAddTraits(.isHeader)
            let steps = proposal.reviewSteps
            if !steps.isEmpty, steps.count == RecordPresentation.records(proposal.plan?["steps"]).count {
                ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                    Text("\(index + 1). \(step)").font(.body)
                }
            } else {
                Text(proposal.summary).font(.body).textSelection(.enabled)
            }
            Button { focusedField = nil; client.confirm(proposal) } label: {
                Text("Confirm this plan").font(.headline).frame(maxWidth: .infinity, minHeight: 50)
            }
            .buttonStyle(.borderedProminent).disabled(!client.canConfirm)
            .accessibilityIdentifier("confirmProposal")
            Button("Cancel proposal", role: .destructive) { client.cancel(proposal) }
                .frame(maxWidth: .infinity, minHeight: 44).disabled(!client.canAct)
            if !client.canConfirm && !client.busy {
                Text(client.connected ? "Waiting for the lab to acknowledge this preview." : "Reconnect to review a fresh proposal.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(22).background(LabStyle.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 24))
        .id(proposal.id)
        .task(id: "\(proposal.id):\(client.connected)") { if client.connected { client.proposalAppeared(proposal) } }
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
            if let id = frame["evidence_id"]?.string, let path = frame["artifact_url"]?.string {
                EvidenceImage(client: client, id: id, path: path, scope: client.evidenceScope)
            } else {
                Text("Scene image unavailable").font(.footnote).foregroundStyle(.secondary)
            }
            evidenceMetadata(frame)
        }
    }

    private func evidenceMetadata(_ record: JSONValue) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            if let title = RecordPresentation.text(record, "description", "summary", "text") { Text(title) }
            Text(RecordPresentation.provenance(record)).font(.caption.bold()).foregroundStyle(LabStyle.teal)
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
                        .font(.caption.bold()).foregroundStyle(LabStyle.teal)
                    Text(observation.text).textSelection(.enabled)
                    metadata("Source", observation.source)
                    if let status = observation.status { metadata("Observer status", status.capitalized) }
                    if observation.checks?.failedChecks == true { metadata("Outcome checks", "One or more checks failed") }
                    ForEach(Array(observation.images.suffix(2).enumerated()), id: \.offset) { _, frame in
                        evidenceFrame(frame)
                    }
                }.padding(.vertical, 4)
            }
            if lab.experiment.id == "red_cabbage_ph", ["reflecting", "complete", "stopped"].contains(lab.trial.state),
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
                if client.sendText(message) { message = ""; focusedField = nil }
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
                    Text(entry.role == "user" ? "YOU" : "OPENARMS").font(.caption.bold()).foregroundStyle(.secondary)
                    Text(entry.text).font(.body).textSelection(.enabled)
                }
                .padding(16).frame(maxWidth: .infinity, alignment: .leading)
                .background(entry.role == "user" ? LabStyle.purple.opacity(0.08) : Color.white.opacity(0.8), in: RoundedRectangle(cornerRadius: 18))
                .accessibilityElement(children: .combine)
            }
        }
    }

    private func history(_ lab: LabSnapshot) -> some View {
        DisclosureGroup(isExpanded: $showHistory) {
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
                            .font(.caption.bold()).foregroundStyle(LabStyle.teal)
                        Text(observation.text).font(.subheadline)
                    }
                }
            }.padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)
        } label: { Label("Trial notebook", systemImage: "book.closed").font(.headline).frame(minHeight: 44) }
        .padding(20).card()
    }

    private func noticeCard(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("A quick note", systemImage: "info.circle").font(.headline)
            Text(text).font(.subheadline)
            if client.needsMicrophoneSettings {
                Button("Open microphone settings") { openSettings() }.frame(minHeight: 44)
            }
            if !client.connected && !client.connecting {
                Button("Lab connection") { showConnection = true }.frame(minHeight: 44)
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
                            .frame(maxWidth: .infinity, maxHeight: 260)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .accessibilityLabel("Captured scene image")
                    case .unavailable:
                        Text("Scene image unavailable").font(.footnote).foregroundStyle(.secondary)
                    }
                } else {
                    ProgressView("Loading scene image").controlSize(.small)
                }
            } else {
                Text("Connect to view the scene image").font(.footnote).foregroundStyle(.secondary)
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
    func card() -> some View { background(Color.white.opacity(0.55), in: RoundedRectangle(cornerRadius: 24)) }
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
                    Text("Use the trusted server address from your lab host. Your private session is saved securely on this iPhone. Provider keys stay on the server.")
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
                Section("Microphone & recovery") {
                    Text("Voice asks for microphone access when you tap Talk. Text does not need it. If you leave the app, audio stops; returning restores the same saved lab without replaying commands.")
                    Button("Open app settings") { openSettings() }.frame(minHeight: 44)
                }
            }
            .navigationTitle("Lab connection").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { pairingCode = ""; dismiss() } }
        }.tint(LabStyle.purple)
    }
}
@MainActor private func openSettings() {
    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
}
