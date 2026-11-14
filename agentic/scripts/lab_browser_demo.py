#!/usr/bin/env python3
"""Headless, mock-only student workflow; saves screenshots, exports and snapshots.

Run with the lab server already running, using a Python environment with Playwright:
  python agentic/scripts/lab_browser_demo.py --url http://127.0.0.1:8000
Add --compose for ONE real expert composition, followed by mock test/promotion.
Mobile coverage uses Chromium with an iPhone-sized viewport and Safari user agent;
it is not an iOS Simulator, Safari engine, hardware, or accessibility-user test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def snapshot(page):
    return page.evaluate("window.openArmsApp.snapshot")


def wait(page, expression):
    page.wait_for_function(expression, timeout=20000)


def check_voice_lifecycle(page):
    """A late permission result must stop its tracks and must never open a socket."""
    return page.evaluate("""async () => {
      const {LiveClient} = await import('/live-client.js');
      const original = navigator.mediaDevices.getUserMedia;
      let resolve, requests = 0, stopped = 0, sockets = 0;
      navigator.mediaDevices.getUserMedia = () => { requests++; return new Promise(r => {resolve = r;}); };
      try {
        const client = new LiveClient('lifecycle-check');
        client._initAudioContext = async () => {};
        client._connectWebSocket = () => {sockets++;};
        const first = client.startVoice();
        await Promise.resolve();
        await client.startVoice();
        client.cleanup();
        resolve({getTracks: () => [{stop: () => {stopped++;}}]});
        await first;
        if (requests !== 1 || stopped !== 1 || sockets !== 0 || client.status !== 'disconnected') throw Error('Voice lifecycle check failed');
        return {requests, stopped, sockets};
      } finally { navigator.mediaDevices.getUserMedia = original; }
    }""")


def screenshot(page, path):
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(path), full_page=True)


def run(page, url, output, label, compose=False):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    wait(page, "window.openArmsApp?.snapshot?.experiment")
    assert snapshot(page)["backend"] == "mock", "This demo must never control hardware."
    lifecycle = check_voice_lifecycle(page)
    page.locator("#prediction-input").fill("I predict Sample C will sink because it is denser than water.")
    # Stream refresh must not erase a student draft.
    page.evaluate("window.openArmsApp._updateSnapshot(structuredClone(window.openArmsApp.snapshot))")
    assert "Sample C" in page.locator("#prediction-input").input_value()
    page.locator("#btn-submit-prediction").click()
    wait(page, "window.openArmsApp.snapshot.prediction.includes('Sample C')")
    page.locator("#command-input").fill("test sample at A in B")
    page.locator("#command-form button").click()
    wait(page, "window.openArmsApp.snapshot.pending?.parameters.source === 'A'")
    original = snapshot(page)["pending"]["request_id"]
    page.locator("#proposal-correct-input").fill("test sample at C in B")
    page.locator("#btn-submit-correction").click()
    wait(page, "window.openArmsApp.snapshot.pending?.parameters.source === 'C'")
    corrected = snapshot(page)["pending"]["request_id"]
    assert original != corrected
    assert next(r for r in snapshot(page)["requests"] if r["request_id"] == original)["status"] == "cancelled"
    screenshot(page, output / f"{label}-proposal.png")
    page.locator("#btn-confirm-proposal").click()
    wait(page, "window.openArmsApp.snapshot.requests.at(-1)?.status === 'executing'")
    wait(page, "window.openArmsApp.snapshot.requests.at(-1)?.status === 'completed'")
    first = snapshot(page)
    assert {o["provenance"] for o in first["observations"]} >= {"MOCK", "MODEL-PREDICTED"}
    assert page.locator("#station-c-contents").inner_text() == "empty"
    assert "MOCK" in page.locator("#observations-list").inner_text()
    assert "MODEL-PREDICTED" in page.locator("#observations-list").inner_text()
    wait(page, "window.openArmsApp.snapshot.quiz !== null")
    question = snapshot(page)["quiz"]
    if question["type"] == "multiple_choice":
        page.locator('input[name="quiz_choice"]').first.check()
    else:
        page.locator("#quiz-freeform-input").fill("Sample A is less dense than water and floats; Sample C is denser and sinks. Volume, fluid density and release are controlled. Mock and model results are not physical observations.")
    before = len(snapshot(page)["notebook"])
    page.locator("#btn-submit-quiz").click()
    wait(page, f"window.openArmsApp.snapshot.notebook.length > {before}")
    assert any("answer" in e["kind"] or "assess" in e["kind"] for e in snapshot(page)["notebook"])
    page.locator("#btn-prepare-trial").click()
    wait(page, "!window.openArmsApp.snapshot.prediction && !window.openArmsApp.snapshot.state.point_holds.B")
    page.locator("#prediction-input").fill("I predict Sample A floats because its density is lower than water.")
    page.locator("#btn-submit-prediction").click()
    wait(page, "window.openArmsApp.snapshot.prediction.includes('Sample A')")
    page.locator("#command-input").fill("test sample at A in B")
    page.locator("#command-form button").click()
    wait(page, "window.openArmsApp.snapshot.pending?.parameters.source === 'A'")
    page.locator("#btn-confirm-proposal").click()
    wait(page, "window.openArmsApp.snapshot.requests.at(-1)?.status === 'completed'")
    final = snapshot(page)
    assert len([r for r in final["requests"] if r["status"] == "completed"]) == 2
    assert {o.get("value") for o in final["observations"] if o["provenance"] == "MODEL-PREDICTED"} >= {"floats", "sinks"}
    with page.expect_download() as download:
        page.locator("#btn-export-notebook").click()
    export = output / f"{label}-notebook.md"
    download.value.save_as(str(export))
    report = export.read_text()
    assert "MOCK" in report and "MODEL-PREDICTED" in report and corrected in report
    sid = final["session_id"]
    page.reload()
    wait(page, "window.openArmsApp?.snapshot?.observations.length >= 4")
    assert snapshot(page)["session_id"] == sid
    assert len(snapshot(page)["notebook"]) >= len(final["notebook"])
    # A response from a retired session must never change the current session.
    page.evaluate("window.openArmsApp._updateSnapshot({...structuredClone(window.openArmsApp.snapshot),session_id:'retired-session'})")
    assert snapshot(page)["session_id"] == sid
    screenshot(page, output / f"{label}-results.png")
    page.locator("#dev-panel").evaluate("e => e.open = true")
    page.locator("#btn-refresh-skills").click()
    wait(page, "document.querySelectorAll('.btn-test-skill').length > 0")
    with page.expect_response(lambda r: "/api/skills/" in r.url and r.url.endswith("/test")) as response:
        page.locator(".btn-test-skill").first.click()
    evidence = response.value.json()
    if response.value.ok:
        assert evidence.get("evidence_id") and evidence.get("verdict") == "passed"
    candidate = None
    if compose:
        page.locator("#skill-compose-input").fill("Create a reusable known-station transfer for a sample from source A or C to destination B. Use the calibrated transfer controller and the object/source/destination parameters. No arbitrary motion or new routes.")
        with page.expect_response(lambda r: r.url.endswith("/api/skills/compose"), timeout=60000) as response:
            page.locator("#btn-compose-skill").click()
        if not response.value.ok:
            candidate = {"error": response.value.text(), "http_status": response.value.status}
        else:
            candidate = response.value.json()
        if "error" not in candidate:
            candidate = finish_candidate(page, candidate)
    assert page.evaluate("document.body.scrollWidth <= innerWidth"), "Page horizontally overflows"
    assert not errors, errors
    (output / f"{label}-snapshot.json").write_text(json.dumps(snapshot(page), indent=2) + "\n")
    return {"label": label, "session_id": sid, "completed_trials": 2, "page_errors": errors,
            "health": page.evaluate("window.openArmsApp.health"),
            "registry_test": evidence, "candidate": candidate, "voice_lifecycle": lifecycle, "viewport": page.viewport_size}


def finish_candidate(page, candidate):
    assert candidate.get("skill_id")
    page.locator("#composed-candidate-preview").wait_for(state="visible")
    assert page.locator("#btn-promote-candidate").is_disabled()
    with page.expect_response(lambda r: r.url.endswith("/test")) as response:
        page.locator("#btn-test-candidate").click()
    assert response.value.ok, response.value.text()
    candidate_evidence = response.value.json()
    assert candidate_evidence["evidence_id"] and candidate_evidence["verdict"] == "passed"
    with page.expect_response(lambda r: r.url.endswith("/promote")) as response:
        page.locator("#btn-promote-candidate").click()
    assert response.value.ok, response.value.text()
    assert response.value.json()["status"] == "active"
    return {"artifact": candidate, "test_evidence": candidate_evidence, "promotion": response.value.json()}


def voice_smoke(browser, url, output):
    """Chromium is launched with a fake file device: never records a person's mic."""
    context = browser.new_context(permissions=["microphone"], viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page.goto(url)
        wait(page, "window.openArmsApp?.snapshot?.experiment")
        assert snapshot(page)["backend"] == "mock"
        page.locator("#prediction-input").fill("I predict Sample A floats because its density is lower than water.")
        page.locator("#btn-submit-prediction").click()
        wait(page, "window.openArmsApp.snapshot.prediction.length > 0")
        await_start = page.locator("#btn-toggle-mic")
        await_start.click()
        page.wait_for_function("['active','unavailable','error'].includes(window.openArmsApp.liveClient?.status)", timeout=30000)
        if page.evaluate("window.openArmsApp.liveClient.status") == "active":
            page.evaluate("""() => { const c = window.openArmsApp.liveClient;
              c.receivedAudioChunks = 0; const original = c._play24kPcmChunk.bind(c);
              c._play24kPcmChunk = data => { c.receivedAudioChunks++; original(data); };
            }""")
            page.wait_for_timeout(6000)
            page.evaluate("window.openArmsApp.liveClient.setMuted(true); window.openArmsApp.liveClient.sendAudioEnd()")
            try:
                page.wait_for_function("window.openArmsApp.snapshot.pending !== null || window.openArmsApp.liveClient.receivedAudioChunks > 0", timeout=45000)
            except Exception:
                pass  # Save the actual bounded outcome, including provider silence.
        result = {"voice_status": page.evaluate("window.openArmsApp.liveClient.status"),
                  "received_audio_chunks": page.evaluate("window.openArmsApp.liveClient.receivedAudioChunks || 0"),
                  "transcript": page.locator("#transcript-feed").inner_text(), "snapshot": snapshot(page),
                  "input": "Generated speech via Chromium fake audio file; no person or hardware recorded."}
        page.evaluate("window.openArmsApp.liveClient.cleanup()")
        screenshot(page, output / "fake-microphone.png")
        (output / "fake-microphone.json").write_text(json.dumps(result, indent=2) + "\n")
        return {key: value for key, value in result.items() if key != "snapshot"}
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("outputs/lab-evidence/browser"))
    parser.add_argument("--compose", action="store_true", help="Allow one real expert composition on desktop")
    parser.add_argument("--fake-audio", type=Path, help="Optional generated speech WAV for a real provider microphone smoke; never uses the actual microphone")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        flags = []
        if args.fake_audio:
            assert args.fake_audio.is_file(), args.fake_audio
            flags = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                     f"--use-file-for-fake-audio-capture={args.fake_audio.resolve()}"]
        browser = p.chromium.launch(headless=True, args=flags)
        voice = None
        try:
            for label, options in (
                ("desktop", {"viewport": {"width": 1440, "height": 1000}}),
                ("mobile-emulation", {"viewport": {"width": 390, "height": 844}, "is_mobile": True,
                 "has_touch": True, "device_scale_factor": 3,
                 "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"}),
            ):
                context = browser.new_context(accept_downloads=True, **options)
                context.tracing.start(screenshots=True, snapshots=True, sources=False)
                try:
                    result = run(context.new_page(), args.url, args.output, label, args.compose and label == "desktop")
                    results.append(result)
                    print(f"PASS {label}: two mock trials, correction, quiz, export/reload; registry diagnostic recorded", flush=True)
                finally:
                    context.tracing.stop(path=str(args.output / f"{label}-trace.zip"))
                    context.close()
            if args.fake_audio:
                voice = voice_smoke(browser, args.url, args.output)
        finally:
            browser.close()
    (args.output / "browser-summary.json").write_text(json.dumps({"results": results, "fake_microphone": voice,
        "coverage_limit": "Headless Chromium desktop and iPhone-sized Safari-user-agent emulation; no iOS Simulator, Safari engine, physical arm, or student usability validation."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
