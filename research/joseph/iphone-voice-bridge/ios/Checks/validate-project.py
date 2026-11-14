#!/usr/bin/env python3
"""Structural checks only: this does not resolve an iOS SDK or build an app."""
import json
from pathlib import Path
import plistlib
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
project_path = root / "OpenArmsVoice.xcodeproj/project.pbxproj"
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", str(project_path)]))
objects = project["objects"]
target = next(o for o in objects.values() if o.get("isa") == "PBXNativeTarget")
assert target["productType"] == "com.apple.product-type.application"
source_phase = next(objects[x] for x in target["buildPhases"] if objects[x]["isa"] == "PBXSourcesBuildPhase")
sources = {objects[objects[x]["fileRef"]]["path"] for x in source_phase["files"]}
assert sources == {p.name for p in (root / "OpenArmsVoice").glob("*.swift")}
for source in sources:
    assert (root / "OpenArmsVoice" / source).is_file()
configs = objects[target["buildConfigurationList"]]["buildConfigurations"]
for config in configs:
    settings = objects[config]["buildSettings"]
    assert settings["CODE_SIGN_STYLE"] == "Automatic"
    assert int(settings["TARGETED_DEVICE_FAMILY"]) == 1
    assert (root / settings["INFOPLIST_FILE"]).is_file()
project_configs = objects[objects[project["rootObject"]]["buildConfigurationList"]]["buildConfigurations"]
assert all(float(objects[c]["buildSettings"]["IPHONEOS_DEPLOYMENT_TARGET"]) == 17 for c in project_configs)
with (root / "OpenArmsVoice/Info.plist").open("rb") as stream:
    info = plistlib.load(stream)
assert info["NSMicrophoneUsageDescription"] and info["NSLocalNetworkUsageDescription"]
assert info["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
assert "UIBackgroundModes" not in info
scheme = ET.parse(root / "OpenArmsVoice.xcodeproj/xcshareddata/xcschemes/OpenArmsVoice.xcscheme")
for reference in scheme.findall(".//BuildableReference"):
    assert objects[reference.attrib["BlueprintIdentifier"]] is target
print("PASS: Xcode project source membership, iOS 17 target, signing, scheme, permissions, and local-only ATS")
