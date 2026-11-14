"""Continuous voice E2E: synthetic speech -> browser worklet -> Gemini -> mock app.

Uses a generated MediaStream, never the person's microphone or physical hardware.
One Start voice click and one socket throughout; every subsequent control is audio.
Requires macOS say/afconvert, Playwright, a running configured MOCK lab.
"""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import time
from playwright.sync_api import sync_playwright


def run(url, output):
    output.mkdir(parents=True, exist_ok=True)
    steps = [
        ('Choose the color dilution experiment.', "s.experiment.id === 'color_dilution'"),
        ('My prediction is that adding water will make the dye lighter because its concentration decreases.', "s.prediction.length > 0"),
        ('Add the water portion from station A into station B.', "s.pending?.parameters.source === 'A'"),
        ('Correction. Use the water portion from station C into station B instead.', "s.pending?.parameters.source === 'C'"),
        ('Cancel that request.', "s.pending === null && s.requests.at(-1)?.status === 'cancelled'"),
        ('Add the water portion from station A into station B.', "s.pending?.parameters.source === 'A'"),
        ('Confirm.', "s.requests.at(-1)?.status === 'completed' && s.quiz !== null"),
        ('My answer is that the concentration decreased because the same amount of dye is in a larger volume of water.', "s.quiz?.answered === true"),
        ('Prepare the next trial.', "s.prediction === '' && s.quiz === null"),
        ('My prediction is that the larger water portion at C will dilute the dye more than A.', "s.prediction.length > 0"),
        ('Add the water portion from station C into station B.', "s.pending?.parameters.source === 'C'"),
        ('Yes, confirm.', "s.requests.filter(r => r.status === 'completed').length === 2 && s.quiz !== null"),
        ('My answer is that C has a lower concentration. The amount of dye stayed constant, and the added water volume changed.', "s.quiz?.answered === true"),
    ]
    clips = []
    for i, (text, _) in enumerate(steps):
        aiff, wav = output / f'voice-{i:02}.aiff', output / f'voice-{i:02}.wav'
        subprocess.run(['say', '-r', '155', '-o', str(aiff), text], check=True)
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', str(aiff), str(wav)], check=True)
        aiff.unlink()
        clips.append(base64.b64encode(wav.read_bytes()).decode())
    evidence = {'input': 'macOS generated speech into synthetic browser MediaStream; no human microphone', 'steps': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(url)
            page.wait_for_function('window.openArmsApp?.snapshot?.experiment')
            assert page.evaluate('window.openArmsApp.snapshot.backend') == 'mock'
            page.evaluate('''() => {
              window.__micRequests = 0; window.__sockets = 0; window.__audioChunks = 0;
              const NativeSocket = window.WebSocket;
              window.WebSocket = class extends NativeSocket {constructor(...args) {super(...args); if(args[0].endsWith('/live')) window.__sockets++;}};
              navigator.mediaDevices.getUserMedia = async () => {
                window.__micRequests++;
                const ctx = new AudioContext(); await ctx.resume();
                const destination = ctx.createMediaStreamDestination();
                window.__syntheticMic = {ctx, destination};
                return destination.stream;
              };
            }''')
            page.locator('#btn-toggle-mic').click()
            page.wait_for_function("window.openArmsApp.liveClient?.status === 'active'", timeout=40000)
            page.evaluate('''() => {const c=window.openArmsApp.liveClient; const original=c._play24kPcmChunk.bind(c);
              c._play24kPcmChunk = data => {window.__audioChunks++; original(data);};}''')
            # Let the short welcome finish before the first utterance.
            page.wait_for_timeout(10000)
            for (text, condition), encoded in zip(steps, clips):
                start = time.monotonic()
                page.evaluate('''async data => {
                  const mic=window.__syntheticMic;
                  const bytes=Uint8Array.from(atob(data), c=>c.charCodeAt(0));
                  const buffer=await mic.ctx.decodeAudioData(bytes.buffer);
                  const source=mic.ctx.createBufferSource(); source.buffer=buffer;
                  source.connect(mic.destination); source.start();
                  await new Promise(resolve=>{source.onended=resolve;});
                }''', encoded)
                try:
                    page.wait_for_function(f"() => {{const s=window.openArmsApp.snapshot;return {condition};}}", timeout=55000)
                    evidence['steps'].append({'text': text, 'passed': True, 'seconds': round(time.monotonic()-start, 2)})
                    print(f'PASS voice: {text}', flush=True)
                    page.wait_for_timeout(4500)
                except Exception:
                    evidence['steps'].append({'text': text, 'passed': False, 'seconds': round(time.monotonic()-start, 2)})
                    raise
            evidence['passed'] = True
            assert page.evaluate('window.__micRequests') == 1
            assert page.evaluate('window.__sockets') == 1
            assert not errors
        finally:
            evidence.update(microphone_requests=page.evaluate('window.__micRequests || 0'), live_sockets=page.evaluate('window.__sockets || 0'),
                            received_audio_chunks=page.evaluate('window.__audioChunks || 0'), browser_errors=errors,
                            snapshot=page.evaluate('window.openArmsApp.snapshot'), transcript=page.locator('#transcript-feed').inner_text())
            page.screenshot(path=str(output / 'continuous-voice.png'), full_page=True)
            page.evaluate('window.openArmsApp.liveClient?.cleanup()')
            evidence['final_voice_status'] = page.evaluate('window.openArmsApp.liveClient?.status')
            (output / 'continuous-voice.json').write_text(json.dumps(evidence, indent=2)+'\n')
            browser.close()
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('outputs/lab-evidence/continuous-voice'))
    args = parser.parse_args()
    result = run(args.url, args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('snapshot','transcript')}))
