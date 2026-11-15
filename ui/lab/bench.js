// Real-bench lane: camera look, simulated preview, then the real arm. Same-computer only.
// Polls /api/bench; everything shown comes from the server's state.
const $ = (id) => document.getElementById(id);
let state = null;
let shownVideo = null;
let shownFrame = null;
let shownSide = null;

async function call(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? { Accept: 'application/json' } : { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store', credentials: 'same-origin',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `The bench request failed (${response.status}).`);
  return data;
}

function render(next) {
  state = next;
  const section = $('bench');
  if (!next || !next.enabled) { section.hidden = true; return; }
  section.hidden = false;
  const target = next.arm === 'real' ? 'the real arm' : 'the stand-in arm';
  if (next.mode === 'rulers') $('bench-text').placeholder = 'move the mandarin from A to B';
  $('bench-arm').textContent = `${next.arm === 'real' ? 'Real arm' : 'Stand-in arm (nothing moves)'} · ${next.mode === 'rulers' ? (next.object_cm ? `mandarin at (${next.object_cm[0]}, ${next.object_cm[1]}) cm, nearest ${next.object_at || 'no place'}` : 'placed by the rulers; no mandarin seen yet') : 'object at ' + (next.object_at || 'no station')}`
    + (next.armed ? '' : ' · DISARMED, restart the server') + (next.busy ? ` · ${next.busy}…` : '');

  const cam = next.camera || {};
  $('bench-sight').textContent = cam.text || '';
  $('bench-look').hidden = cam.status === 'no_camera';
  const frame = $('bench-frame');
  if (cam.frame) {
    if (shownFrame !== cam.frame) { shownFrame = cam.frame; frame.src = cam.frame; }
    frame.hidden = false; $('bench-frame-empty').hidden = true;
  } else { frame.hidden = true; $('bench-frame-empty').hidden = false; $('bench-frame-empty').textContent = cam.status === 'no_camera' ? 'No camera configured.' : 'No picture yet. Press Look now.'; }

  const side = next.side || {};
  $('bench-side').hidden = !side.frame;
  if (side.frame && shownSide !== side.frame) { shownSide = side.frame; $('bench-side-frame').src = side.frame; }
  $('bench-side-text').textContent = side.text || '';
  // "Look now" refreshes whichever cameras exist.
  $('bench-look').hidden = cam.status === 'no_camera' && side.text === null;

  const pending = next.pending;
  const preview = pending ? pending.preview || {} : {};
  const video = $('bench-video');
  if (preview.video) {
    if (shownVideo !== preview.video) { shownVideo = preview.video; video.src = preview.video; video.play?.().catch(() => {}); }
    video.hidden = false; $('bench-video-empty').hidden = true;
  } else {
    video.hidden = true; video.removeAttribute('src'); shownVideo = null;
    $('bench-video-empty').hidden = false;
    $('bench-video-empty').textContent = pending && preview.status === 'running' ? 'Simulating…' : 'Ask for an action to see it simulated first.';
  }
  $('bench-preview-badge').hidden = !preview.video;
  $('bench-preview-status').textContent = !pending ? '' : ({
    running: 'Simulating this plan in MuJoCo…',
    ready: `Simulation finished. Type execute, or press Execute, to run it on ${target}.`,
    blocked: 'The simulation stopped this plan. It will not be executed.',
    error: `The simulation did not run: ${preview.reason || 'unknown error'}`,
  }[preview.status] || '');
  const overridden = pending && pending.sim_block_overridden && preview.status === 'blocked';
  if (overridden) {
    $('bench-preview-status').textContent = `Warning: the simulation's own pour had a problem, but Execute replays the recorded pour on ${target}, which the simulation did not check. Watch it and keep Stop at hand.`;
  }

  const summary = $('bench-summary');
  summary.hidden = !pending;
  summary.textContent = pending ? `Plan: ${pending.summary}` : '';
  const notes = $('bench-notes');
  notes.replaceChildren();
  for (const [kind, items] of [['blocked', preview.blocks || []], ['note', preview.warnings || []]]) {
    for (const text of items) {
      const li = document.createElement('li');
      if (kind === 'blocked') li.className = 'blocked';
      li.textContent = (kind === 'blocked' ? (overridden ? 'Warning (simulation): ' : 'Blocked: ') : 'Note: ') + text;
      notes.appendChild(li);
    }
  }
  const idle = !next.busy;
  const simulationOnly = pending && pending.executable === false;
  $('bench-execute').disabled = !(pending && (preview.status === 'ready' || overridden) && idle && next.armed) || simulationOnly;
  $('bench-execute').textContent = simulationOnly ? 'Simulation only' : `Execute on ${target}`;
  if (simulationOnly && preview.status === 'ready') {
    $('bench-preview-status').textContent = `Simulation finished. ${pending.why_not_executable}`;
  }
  if (preview.predicted && preview.status === 'ready') {
    const li = document.createElement('li');
    const p = preview.predicted;
    li.textContent = `Predicted: ${p.color}${(p.observations || []).length ? ' with ' + p.observations.join(' and ') : ''}`;
    notes.prepend(li);
  }
  $('bench-cancel').disabled = !(pending && idle);

  // The bench operator's question (real arm): answered here instead of in the server terminal.
  const question = next.question;
  $('bench-question').hidden = !question;
  if (question) {
    $('bench-question-text').textContent = question.text;
    $('bench-question').dataset.id = question.id;
  }

  const result = $('bench-result');
  result.hidden = !next.last_result;
  if (next.last_result) {
    result.dataset.provenance = next.last_result.provenance;
    result.textContent = `${next.last_result.provenance}: ${next.last_result.text}`;
  }
  const log = $('bench-log');
  log.replaceChildren(...(next.log || []).map((entry) => {
    const p = document.createElement('p');
    p.textContent = `${entry.role === 'user' ? 'You' : 'Bench'}: ${entry.text}`;
    return p;
  }));
}

async function act(path, body) {
  try { render(await call(path, body)); }
  catch (error) { $('bench-preview-status').textContent = error.message; }
}

async function poll() {
  try { render(await call('/api/bench')); } catch { /* server restarting */ }
  if (!state || state.enabled !== false) setTimeout(poll, 1000);
}

window.addEventListener('DOMContentLoaded', () => {
  if (!$('bench')) return;
  $('bench-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const text = $('bench-text').value.trim();
    if (!text) return;
    $('bench-text').value = '';
    $('bench-preview-status').textContent = 'Working…';
    act('/api/bench/request', { text });
  });
  $('bench-execute').addEventListener('click', () => state?.pending && act('/api/bench/execute', { request_id: state.pending.request_id }));
  $('bench-cancel').addEventListener('click', () => act('/api/bench/cancel', {}));
  $('bench-stop').addEventListener('click', () => act('/api/bench/stop', {}));
  const answer = (yes) => { const id = $('bench-question').dataset.id; if (id) { $('bench-question').hidden = true; act('/api/bench/answer', { question_id: id, yes }); } };
  $('bench-yes').addEventListener('click', () => answer(true));
  $('bench-no').addEventListener('click', () => answer(false));
  $('bench-look').addEventListener('click', () => act('/api/bench/look', {}));
  poll();
});
