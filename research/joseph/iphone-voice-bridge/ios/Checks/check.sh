#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .build/ModuleCache
export CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache"
export SWIFT_MODULECACHE_PATH="$PWD/.build/ModuleCache"
swiftc -frontend -parse OpenArmsVoice/*.swift
swiftc -swift-version 5 -warnings-as-errors -typecheck -module-cache-path "$PWD/.build/ModuleCache" OpenArmsVoice/ProtocolCore.swift
swift test
plutil -lint OpenArmsVoice/Info.plist OpenArmsVoice.xcodeproj/project.pbxproj
python3 Checks/validate-project.py
printf '%s\n' 'PASS: Swift syntax parse for all app sources; Foundation core typecheck and streaming XCTest suite. No iOS build performed.'
