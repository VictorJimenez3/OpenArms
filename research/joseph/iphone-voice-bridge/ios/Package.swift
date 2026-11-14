// swift-tools-version: 5.9
import PackageDescription

// Portable protocol checks only; the app itself is built with the Xcode project.
let package = Package(
    name: "VoiceProtocol",
    platforms: [.macOS(.v13)],
    products: [.library(name: "VoiceProtocol", targets: ["VoiceProtocol"])],
    targets: [
        .target(name: "VoiceProtocol", path: "OpenArmsVoice",
                exclude: ["AudioPipeline.swift", "VoiceClient.swift", "VoiceScreen.swift", "OpenArmsVoiceApp.swift", "Info.plist"],
                sources: ["ProtocolCore.swift"]),
        .testTarget(name: "ProtocolCoreTests", dependencies: ["VoiceProtocol"], path: "Tests/ProtocolCoreTests")
    ]
)
