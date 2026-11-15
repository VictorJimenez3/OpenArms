// Voice for the Real bench panel: microphone -> /api/bench/voice (Gemini Live) -> speaker.
// What the student asks goes to the same bench request as typing; the arm still needs Execute and the operator's Yes.
const $ = (id) => document.getElementById(id);

function encode(buffer) {
  const bytes = new Uint8Array(buffer);
  let s = '';
  for (let i = 0; i < bytes.length; i += 4096) s += String.fromCharCode(...bytes.subarray(i, i + 4096));
  return btoa(s);
}

let voice = null;

function status(text) { $('bench-voice-status').textContent = text; }

function line(role, text) {
  $(role === 'user' ? 'bench-voice-heard' : 'bench-voice-said').textContent = text ? `${role === 'user' ? 'You said' : 'Voice'}: ${text}` : '';
}

async function start() {
  if (voice) return;
  if (!isSecureContext || !navigator.mediaDevices?.getUserMedia) { status('Voice needs localhost or HTTPS.'); return; }
  const context = new (window.AudioContext || window.webkitAudioContext)();
  await context.resume();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch { context.close(); status('Microphone blocked. Allow it in the browser, then try again.'); return; }
  await context.audioWorklet.addModule(new URL('./audio-worklet.js', import.meta.url));
  const source = context.createMediaStreamSource(stream);
  const worklet = new AudioWorkletNode(context, 'pcm-capture-processor');
  const silent = context.createGain(); silent.gain.value = 0;
  source.connect(worklet); worklet.connect(silent); silent.connect(context.destination);

  const url = new URL('/api/bench/voice', location.href);
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(url);
  const playing = new Set();
  let next = 0;
  voice = { context, stream, ws, worklet, playing };

  const clearSpeech = () => { for (const s of playing) { try { s.stop(); } catch {} } playing.clear(); next = context.currentTime; };
  worklet.port.onmessage = ({ data }) => {
    if (data.type === 'pcm' && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'audio', data: encode(data.buffer) }));
  };
  ws.onopen = () => { worklet.port.postMessage({ type: 'gate', enabled: true, epoch: 1 }); status('Connecting to Gemini…'); };
  ws.onmessage = ({ data }) => {
    let f; try { f = JSON.parse(data); } catch { return; }
    if (f.type === 'audio') {
      const bin = atob(f.data);
      const view = new DataView(Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer);
      const pcm = new Float32Array(bin.length / 2);
      for (let i = 0; i < pcm.length; i++) pcm[i] = view.getInt16(i * 2, true) / 32768;
      const buf = context.createBuffer(1, pcm.length, 24000);
      buf.copyToChannel(pcm, 0);
      const src = context.createBufferSource();
      src.buffer = buf; src.connect(context.destination);
      const at = Math.max(context.currentTime + 0.02, next);
      next = at + buf.duration;
      playing.add(src); src.onended = () => playing.delete(src);
      src.start(at);
    } else if (f.type === 'interrupted') clearSpeech();
    else if (f.type === 'transcript') line(f.role, f.text);
    else if (f.type === 'status') {
      status(f.message || ({ connecting: 'Connecting to Gemini…', listening: `Listening${f.model ? ` (${f.model})` : ''}. Say "stop" any time to stop the arm.` }[f.status] || f.status));
      if (f.status === 'unavailable') stop(false);
    } else if (f.type === 'error') status(f.message);
  };
  ws.onclose = () => { if (voice && voice.ws === ws) stop(false); };
  $('bench-voice').textContent = 'Stop voice';
  $('bench-voice').setAttribute('aria-pressed', 'true');
}

function stop(say = true) {
  const v = voice; voice = null;
  if (!v) return;
  try { v.ws.send(JSON.stringify({ type: 'close' })); } catch {}
  try { v.ws.close(); } catch {}
  for (const s of v.playing) { try { s.stop(); } catch {} }
  v.stream.getTracks().forEach((t) => t.stop());
  v.worklet.port.onmessage = null;
  v.context.close().catch(() => {});
  $('bench-voice').textContent = 'Talk';
  $('bench-voice').setAttribute('aria-pressed', 'false');
  if (say) status('Voice off. Typing still works.');
}

window.addEventListener('DOMContentLoaded', () => {
  const button = $('bench-voice');
  if (!button) return;
  button.addEventListener('click', () => (voice ? stop() : start().catch((e) => { stop(false); status(`Voice could not start: ${e.message}`); })));
});
