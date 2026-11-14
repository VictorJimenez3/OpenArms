import SwiftUI
import UIKit

struct VoiceScreen: View {
    @StateObject private var client = VoiceClient()
    @AppStorage("relayAddress") private var address = "ws://MAC-HOST.local:8765/voice"
    @Environment(\.scenePhase) private var scenePhase
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Label(client.state, systemImage: client.microphoneActive ? "mic.fill" : "waveform")
                        .font(.largeTitle.bold())
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("connectionState")
                    Text(client.detail).font(.title3)
                    Label(client.microphoneActive ? "Microphone on" : "Microphone off",
                          systemImage: client.microphoneActive ? "mic.fill" : "mic.slash.fill")
                        .font(.headline)
                    if client.connected, client.serverLogging == true {
                        Label(client.serverRawAudio == true ? "Mac is logging transcripts and audio" : "Mac is logging transcripts",
                              systemImage: "doc.text")
                            .font(.subheadline)
                    }

                    if let message = client.errorMessage {
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Session notice", systemImage: "exclamationmark.triangle.fill").font(.headline)
                            Text(message).textSelection(.enabled)
                            if client.needsMicrophoneSettings || !client.active {
                                Button("Open app settings") { openAppSettings() }
                                    .frame(minHeight: 44)
                            }
                        }
                        .padding()
                        .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                        .accessibilityElement(children: .contain)
                    }

                    VStack(spacing: 16) {
                        if !client.active {
                            Button { client.start(address: address) } label: {
                                Label("Start session", systemImage: "play.fill")
                                    .frame(maxWidth: .infinity, minHeight: 52)
                            }
                            .buttonStyle(.borderedProminent)
                            .accessibilityHint("Connects to the relay and plays the opening prompt.")
                            .accessibilityIdentifier("startSession")
                        } else {
                            Button { client.toggleMute() } label: {
                                Label(client.muted ? "Unmute microphone" : "Mute microphone",
                                      systemImage: client.muted ? "mic.fill" : "mic.slash.fill")
                                    .frame(maxWidth: .infinity, minHeight: 52)
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(!client.connected || client.ending)
                            .accessibilityHint("Muting stops microphone capture. Relay replies can still play.")
                            .accessibilityIdentifier("toggleMute")

                            Button(role: .destructive) { client.end() } label: {
                                Label("End session", systemImage: "stop.fill")
                                    .frame(maxWidth: .infinity, minHeight: 52)
                            }
                            .buttonStyle(.bordered)
                            .disabled(client.ending)
                            .accessibilityIdentifier("endSession")
                        }
                    }
                    .font(.title3.bold())

                    if !client.replyText.isEmpty {
                        textBlock("Relay reply", text: client.replyText)
                    }
                    if !client.transcript.isEmpty {
                        textBlock("You said", text: client.transcript)
                    }
                    Text("Prototype for conversation testing. Replies may describe simulated results.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                .padding()
                .frame(maxWidth: 700, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("OpenArms Voice")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                Button { showSettings = true } label: {
                    Label("Connection settings", systemImage: "gearshape")
                }
                .accessibilityIdentifier("connectionSettings")
            }
            .sheet(isPresented: $showSettings) {
                DeveloperSettings(client: client, address: $address)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { client.enteredBackground() }
        }
        .onChange(of: client.state) { _, state in
            // Announce state transitions, never the live transcript or every audio frame.
            UIAccessibility.post(notification: .announcement, argument: state)
        }
    }

    private func textBlock(_ title: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            Text(text).font(.body).textSelection(.enabled)
        }
    }
}

private struct DeveloperSettings: View {
    @ObservedObject var client: VoiceClient
    @Binding var address: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Relay connection") {
                    TextField("Relay URL or hostname", text: $address)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .disabled(client.active)
                        .accessibilityLabel("Relay URL or hostname")
                    Text("Default: ws://MAC-HOST.local:8765/voice. Replace MAC-HOST with the Mac’s LocalHostName. A hostname alone uses port 8765 and /voice. End the current session before changing it.")
                    Text("Use trusted Wi-Fi. Local ws:// audio is unencrypted. Use wss:// only with a trusted certificate.")
                }
                Section("Permissions") {
                    Text("Allow Microphone and Local Network when iOS asks. If a connection fails, check Local Network in app settings, the relay address, Mac firewall and Wi-Fi. iOS does not expose a reliable Local Network permission status here.")
                    Button("Open app settings") { openAppSettings() }
                }
                Section("Current or last connection") {
                    LabeledContent("Address", value: client.endpointInUse ?? "Not started")
                    LabeledContent("Session", value: client.sessionID ?? "None")
                    LabeledContent("Relay mode", value: client.serverMode ?? "Unknown")
                    LabeledContent("Server logging", value: status(client.serverLogging))
                    LabeledContent("Server raw audio", value: status(client.serverRawAudio))
                    Text("These logging flags are reported by the relay. This app does not save audio or transcripts to files.")
                }
            }
            .navigationTitle("Connection settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { dismiss() } }
        }
    }

    private func status(_ value: Bool?) -> String {
        value.map { $0 ? "On" : "Off" } ?? "Unknown"
    }
}

private func openAppSettings() {
    guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
    UIApplication.shared.open(url)
}
