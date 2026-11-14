import { LabApiClient } from './api.js';
import { SessionClient } from './live-client.js';

const $ = selector => document.querySelector(selector);
const api = new LabApiClient();
let client;
let snapshot;
let busy = false;
let connection = 'connecting';
let pendingKey = '';
let acknowledgedKey = '';
let proposalGeneration = 0;
let sceneView;
const attemptedPresentations = new Set();
const invalidatedProposals = new Set();
const liveTurns = new Map();
const names = { vinegar: 'Vinegar', baking_soda: 'Baking-soda solution', water: 'Water' };
const text = (selector, value) => {
  const element = $(selector);
  const content = value || '';
  if (element.textContent !== content) element.textContent = content;
};
const keyFor = proposal => proposal ? `${proposal.request_id}:${proposal.proposal_version}` : '';
const currentObservation = () => (snapshot?.observations || []).filter(observation => observation.trial_id === snapshot.trial?.trial_id).at(-1);

function notify(message) { text('#notice-text', message); $('#notice').hidden = false; }
function fail(error) { notify(error.message || 'Something interrupted the request. Check your notebook before trying again.'); }
function credentialsNeeded() {
  releaseScene();
  $('#pairing').hidden = false;
  $('#pairing-code').focus();
  text('#connection-label', 'Pairing required');
}
async function boot(pairingCode) {
  try {
    const state = api.sessionId && !pairingCode ? await api.snapshot() : await api.create(pairingCode);
    $('#pairing').hidden = true;
    $('#pairing-code').value = '';
    client?.close();
    if (snapshot?.session_id !== state.session_id) {
      releaseScene();
      snapshot = undefined;
      liveTurns.clear();
      attemptedPresentations.clear();
      invalidatedProposals.clear();
    }
    connection = 'connecting';
    pendingKey = acknowledgedKey = '';
    proposalGeneration++;
    client = new SessionClient(api, { onState: showState, onTranscript: transcript, onStatus: audioStatus, onError: notify, onResync: resync });
    client.acceptState(state);
    client.connect();
  } catch (error) {
    if ([401,403,404].includes(error.status)) { api.forget(); credentialsNeeded(); }
    else { text('#connection-label', 'Notebook unavailable'); fail(error); }
  }
}
async function resync() {
  try { client?.acceptState(await api.snapshot()); }
  catch (error) { fail(error); if ([401,403,404].includes(error.status)) credentialsNeeded(); }
}
async function act(action, body = {}, onSuccess) {
  if (busy || !api.sessionId) return false;
  busy = true; controls();
  try {
    const result = await api.action(action, body);
    if (!client?.acceptState(result) && action === 'request' && result?.task_id) {
      // An enqueue receipt can precede its first state update.
      void resync();
    }
    onSuccess?.();
    $('#notice').hidden = true;
    return true;
  } catch (error) { fail(error); return false; }
  finally { busy = false; controls(); }
}
function showState(state) {
  if (snapshot?.generation !== state.generation) {
    for (const [key, turn] of liveTurns) if (!turn.final) liveTurns.delete(key);
    if (pendingKey) invalidatedProposals.add(pendingKey);
    acknowledgedKey = '';
    proposalGeneration++;
  }
  snapshot = state;
  render();
}
function controls() {
  const ready = Boolean(snapshot) && !busy;
  const complete = Boolean(currentObservation());
  $('#conditions').disabled = !ready || complete;
  $('#prediction').disabled = !ready || complete;
  $('#save-prediction').disabled = $('#prediction').disabled;
  $('#message').disabled = !ready;
  $('#send').disabled = !ready;
  $('#new-trial').disabled = !ready;
  $('#reflection-form button[type=submit]').disabled = !ready;
  $('#confirm').disabled = !ready || connection !== 'connected' || acknowledgedKey !== pendingKey || !pendingKey || invalidatedProposals.has(pendingKey) || expired(snapshot.pending);
  $('#cancel').disabled = !ready;
  $('#answer-clarification').disabled = !ready;
}
function expired(proposal) {
  if (!proposal?.expires_at) return false;
  const value = typeof proposal.expires_at === 'number' ? proposal.expires_at * (proposal.expires_at < 1e12 ? 1000 : 1) : Date.parse(proposal.expires_at);
  return Number.isFinite(value) && value <= Date.now();
}
function render() {
  const trial = snapshot.trial || {};
  for (const element of document.querySelectorAll('[data-condition]')) {
    const chosen = element.dataset.condition === trial.condition_id;
    element.setAttribute('aria-pressed', String(chosen));
    element.querySelector('.choice-mark').textContent = chosen ? '✓' : '+';
  }
  // Keep a student's in-progress correction intact while state updates arrive.
  if (document.activeElement !== $('#prediction') && !$('#prediction').dataset.dirty) $('#prediction').value = snapshot.prediction || '';
  text('#prediction-saved', snapshot.prediction ? 'Prediction saved in your notebook.' : '');
  text('#save-prediction', snapshot.prediction ? 'Update prediction ↗' : 'Save prediction ↗');
  renderMessages();
  renderProposal();
  renderTask();
  renderScene();
  renderSkills();
  renderEvidence();
  renderHistory();
  controls();
}

// Persisted turns are authoritative. Live fragments are coalesced by role + turn ID.
function renderMessages() {
  const turns = new Map();
  for (const [index, message] of (snapshot?.messages || []).entries()) {
    if (!['user','assistant'].includes(message.role) || !message.text) continue;
    const key = `${message.role}:${message.turn_id || message.id || `saved-${index}`}`;
    const existing = turns.get(key);
    turns.set(key, { ...message, text: existing ? joinTurn(existing.text, message.text, false) : message.text });
  }
  for (const [key, turn] of liveTurns) {
    if (!turns.has(key) || !turn.final) turns.set(key, turn);
    else liveTurns.delete(key);
  }
  const log = $('#messages');
  const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 70;
  const fragment = document.createDocumentFragment();
  for (const [key, turn] of turns) {
    const element = document.createElement('article'); element.className = `message ${turn.role}${turn.final === false ? ' draft' : ''}`; element.dataset.turn = key;
    const speaker = document.createElement('span'); speaker.className = 'speaker'; speaker.textContent = turn.role === 'user' ? 'You' : 'OpenArms';
    const paragraph = document.createElement('p'); paragraph.textContent = turn.text;
    element.append(speaker, paragraph); fragment.append(element);
  }
  // Skip identical log rewrites so state heartbeats do not repeat screen-reader announcements.
  const signature = [...turns].map(([key, turn]) => `${key}:${turn.text}:${turn.final}`).join('|');
  if (log.dataset.signature !== signature) { log.replaceChildren(fragment); log.dataset.signature = signature; if (nearBottom) log.scrollTop = log.scrollHeight; }
}
function joinTurn(previous, incoming, final) {
  if (final || incoming.startsWith(previous)) return incoming;
  if (previous.endsWith(incoming)) return previous;
  // Some providers send cumulative text; others send disjoint fragments.
  for (let length = Math.min(previous.length, incoming.length); length > 0; length--) {
    if (previous.endsWith(incoming.slice(0,length))) return previous + incoming.slice(length);
  }
  return previous + (/\s$/.test(previous) || /^[\s.,!?;:]/.test(incoming) ? '' : ' ') + incoming;
}
function transcript(frame) {
  const key = `${frame.role}:${frame.turn_id}`;
  const previous = liveTurns.get(key);
  if (previous?.final) return;
  liveTurns.set(key, { ...frame, text: previous ? joinTurn(previous.text, frame.text, frame.final) : frame.text });
  if (liveTurns.size > 200) liveTurns.delete(liveTurns.keys().next().value);
  renderMessages();
}
function renderProposal() {
  const proposal = snapshot.pending;
  const key = keyFor(proposal);
  if (pendingKey !== key) {
    pendingKey = key; acknowledgedKey = ''; proposalGeneration++;
  }
  $('#proposal').hidden = !proposal;
  $('#jump-to-proposal').hidden = !proposal;
  if (!proposal) return;
  text('#proposal-summary', proposal.summary);
  text('#proposal-status', expired(proposal) ? 'This proposal has expired. Send a new request.' : invalidatedProposals.has(key) ? 'Connection changed. Ask for a fresh proposal before confirming.' : acknowledgedKey === key ? 'Reviewed on screen. Ready for your decision.' : 'Displaying the exact proposal before confirmation…');
  $('#review-again').hidden = !attemptedPresentations.has(key) || acknowledgedKey === key || invalidatedProposals.has(key);
  schedulePresentation();
}
function schedulePresentation(force = false) {
  const proposal = snapshot?.pending;
  const key = keyFor(proposal);
  if (!key || !proposal.summary || expired(proposal) || invalidatedProposals.has(key) || connection !== 'connected' || document.hidden || (!force && attemptedPresentations.has(key))) return;
  const epoch = proposalGeneration;
  // Two animation frames allow the exact visible proposal to be laid out and painted.
  requestAnimationFrame(() => requestAnimationFrame(async () => {
    if (document.hidden || epoch !== proposalGeneration || keyFor(snapshot.pending) !== key || connection !== 'connected' || $('#proposal').hidden || $('#proposal-summary').textContent !== proposal.summary || !$('#proposal-summary').getClientRects().length || attemptedPresentations.has(key)) return;
    // Require actual viewport visibility, not mere delivery or an off-screen DOM node.
    const rect = $('#proposal-summary').getBoundingClientRect();
    const viewport = window.visualViewport;
    const top = viewport?.offsetTop || 0;
    const bottom = Math.min(top + (viewport?.height || innerHeight), $('.voice-dock').getBoundingClientRect().top);
    if (rect.top < top || rect.bottom > bottom) return;
    attemptedPresentations.add(key);
    try {
      const state = await api.action('present', { request_id: proposal.request_id, proposal_version: proposal.proposal_version, channel: 'text' });
      client?.acceptState(state);
      if (keyFor(snapshot.pending) === key && epoch === proposalGeneration && connection === 'connected' && !expired(snapshot.pending)) {
        acknowledgedKey = key;
        renderProposal();
      }
    } catch (error) { fail(error); text('#proposal-status', 'Presentation could not be saved. Review the proposal and try again.'); $('#review-again').hidden = false; }
    controls();
  }));
}
const taskLabels = {
  queued: 'Request queued', running: 'Reviewing your request',
  needs_clarification: 'A question about your request', awaiting_confirmation: 'Waiting for your decision',
  executing: 'Running the confirmed plan', observing: 'Checking the result',
  completed: 'Task complete', failed: 'Task could not finish', cancelled: 'Task canceled',
};
const routeLabels = { active_skill: 'Reused an active skill', expert: 'Background expert' };

function renderTask() {
  const trialId = snapshot.trial?.trial_id;
  const task = snapshot.tasks?.findLast(item => !item.trial_id || item.trial_id === trialId);
  const label = Object.hasOwn(taskLabels, task?.status) ? taskLabels[task.status] : '';
  const question = task?.status === 'needs_clarification';
  const step = task?.feedback?.findLast(event => event.type === 'execution_progress')?.step;
  const detail = task?.summary || task?.reason ||
    (task?.status === 'executing' && Number.isInteger(step) && step >= 0 ? `Step ${step + 1}` : '');
  const route = Object.hasOwn(routeLabels, task?.route) ? routeLabels[task.route] : '';
  $('#task-progress').hidden = !label;
  $('#answer-clarification').hidden = !question;
  text('#task-status', label);
  text('#task-detail', detail);
  text('#task-reason', task?.reason !== detail ? task?.reason : '');
  $('#task-context').hidden = !task?.request && !route;
  text('#task-request', task?.request);
  text('#task-route', route);
}

function releaseScene() {
  if (!sceneView) return;
  sceneView.controller.abort();
  for (const url of sceneView.urls) URL.revokeObjectURL(url);
  sceneView = undefined;
  $('#scene-frames').replaceChildren();
}

async function loadFrame(frame, view, figure, status) {
  let url;
  try {
    const blob = await api.evidenceImage(frame, view.controller.signal);
    if (sceneView !== view) return;
    url = URL.createObjectURL(blob);
    view.urls.add(url);
    const image = document.createElement('img');
    image.alt = frame.description || 'Scene evidence frame';
    image.src = url;
    await image.decode();
    if (sceneView !== view) return;
    figure.prepend(image);
    status.remove();
  } catch {
    if (sceneView !== view) return;
    if (url) {
      URL.revokeObjectURL(url);
      view.urls.delete(url);
    }
    status.textContent = 'Image unavailable.';
  }
}

function captureTime(value) {
  if (value == null) return '';
  const date = typeof value === 'number' ? new Date(value * (value < 1e12 ? 1000 : 1)) : new Date(value);
  return Number.isFinite(date.getTime()) ? `Captured ${date.toLocaleString()}` : '';
}

function renderScene() {
  const scene = snapshot.scene;
  const frames = snapshot.scene_images || [];
  const detail = [scene?.summary, provenanceName(scene?.provenance), scene?.fresh === false ? 'Stale scene' : ''].filter(Boolean).join(' · ');
  $('#scene').hidden = !detail && !frames.length;
  text('#scene-detail', detail);
  const container = $('#scene-frames');
  const signature = JSON.stringify([snapshot.session_id, snapshot.generation,
    frames.map(frame => [frame.evidence_id, frame.captured_at, frame.provenance, frame.sha256, frame.artifact_url, frame.description])]);
  if (sceneView?.signature === signature) return;
  releaseScene();
  if (!frames.length) return;
  const view = { signature, controller: new AbortController(), urls: new Set() };
  sceneView = view;
  container.replaceChildren(...frames.map(frame => {
    const figure = document.createElement('figure');
    const caption = document.createElement('figcaption');
    caption.textContent = [provenanceName(frame.provenance), captureTime(frame.captured_at)].filter(Boolean).join(' · ');
    if (frame.evidence_id || frame.sha256) {
      const details = document.createElement('details');
      details.className = 'lab-details';
      const summary = document.createElement('summary');
      summary.textContent = 'Frame details';
      details.append(summary);
      for (const field of [frame.evidence_id && `Evidence ID: ${frame.evidence_id}`, frame.sha256 && `SHA-256: ${frame.sha256}`].filter(Boolean)) {
        const line = document.createElement('p');
        line.textContent = field;
        details.append(line);
      }
      caption.append(details);
    }
    const status = document.createElement('p');
    status.textContent = 'Loading image…';
    figure.append(status, caption);
    void loadFrame(frame, view, figure, status);
    return figure;
  }));
}

function renderSkills() {
  const skills = snapshot.active_skills || snapshot.skills?.filter?.(skill => skill.status === 'active' || skill.lifecycle === 'active') || [];
  $('#active-skills').hidden = !skills.length;
  $('#skill-labels').replaceChildren(...skills.map(skill => {
    const item = document.createElement('li');
    item.textContent = skill.name || skill.label || skill.skill_id;
    const details = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = 'Skill details';
    const version = document.createElement('p'); version.textContent = `Version: ${skill.version || skill.skill_version}`;
    details.append(summary, version);
    for (const example of skill.retrieval_examples || []) {
      const text = document.createElement('p'); text.textContent = `Try: ${example}`; details.append(text);
    }
    item.append(details);
    return item;
  }));
}

const provenanceLabels = {
  SYNTHETIC: 'Synthetic',
  SIMULATED: 'Simulated',
  RECORDED_REAL: 'Recorded physical evidence',
  UNKNOWN: 'Unknown',
  'MODEL-PREDICTED': 'Model-predicted reference',
};

function provenanceName(provenance) {
  return Object.hasOwn(provenanceLabels, provenance) ? provenanceLabels[provenance] : '';
}

function observationLabel(observation) {
  if (observation.status === 'unknown') return 'UNKNOWN · NO VERIFIED OBSERVATION';
  if (observation.provenance === 'MODEL-PREDICTED') return 'MODEL-PREDICTED · REFERENCE OUTCOME';
  const provenance = provenanceName(observation.provenance);
  return observation.status === 'observed' && provenance && observation.provenance !== 'UNKNOWN'
    ? `OBSERVED · ${provenance.toUpperCase()}` : 'UNKNOWN · NO VERIFIED OBSERVATION';
}

function renderObservationDetails(observation) {
  const fields = Object.entries(observation.features || {})
    .filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value))
    .map(([name, value]) => `${name.replaceAll('_', ' ')}: ${value}`);
  const evidenceIds = (observation.evidence || []).filter(id => typeof id === 'string');
  if (evidenceIds.length) fields.push(`Evidence IDs: ${evidenceIds.join(', ')}`);
  $('#observation-details').hidden = !fields.length;
  $('#observation-fields').replaceChildren(...fields.map(field => {
    const item = document.createElement('li');
    item.textContent = field;
    return item;
  }));
}

function renderEvidence() {
  const observation = currentObservation();
  $('#evidence').hidden = !observation;
  $('#reflection-panel').hidden = !observation;
  $('#new-trial').hidden = !observation;
  if (!observation) return;
  const reference = observation.status !== 'unknown' && observation.provenance === 'MODEL-PREDICTED';
  text('#evidence-provenance', observationLabel(observation));
  text('#evidence-text', observation.text || 'No independent observation is available.');
  text('#evidence-source', typeof observation.source === 'string' ? `Source: ${observation.source}` : '');
  text('#evidence-limit', reference ? 'This mock reference gives an expected color.' : '');
  renderObservationDetails(observation);
  const color = typeof observation.display_color === 'string' && /^#[0-9a-f]{6}$/i.test(observation.display_color) ? observation.display_color : '';
  $('.evidence-swatch').hidden = !reference || !color;
  if (reference && color) $('#evidence').style.setProperty('--result-color', color);
}
function renderHistory() {
  const observations = snapshot.observations || [];
  text('#history-count', observations.length ? `${observations.length} ${observations.length === 1 ? 'trial' : 'trials'} recorded` : 'No trials yet');
  const container = $('#history-list');
  if (!observations.length) return;
  const fragment = document.createDocumentFragment();
  for (const [index, observation] of observations.entries()) {
    const entry = document.createElement('article'); entry.className = 'history-item';
    const title = document.createElement('strong'); title.textContent = `Trial ${index + 1} · ${names[observation.condition_id] || 'Red-cabbage indicator'}`;
    const provenance = document.createElement('span'); provenance.className = 'history-label'; provenance.textContent = observationLabel(observation);
    const result = document.createElement('p'); result.textContent = observation.text || 'No observation recorded.';
    entry.append(title, provenance, result);
    // Notebook schemas may add fields; only render explicit student text, never raw events.
    const records = (snapshot.notebook || []).filter(item => item.trial_id === observation.trial_id);
    for (const item of records) {
      const kind = item.type || item.kind;
      const content = item.text || item.data?.text;
      if (['prediction','reflection'].includes(kind) && typeof content === 'string') {
        const line = document.createElement('p'); line.textContent = `${kind === 'prediction' ? 'Prediction' : 'Reflection'}: ${content}`; entry.append(line);
      }
    }
    fragment.prepend(entry);
  }
  container.replaceChildren(fragment);
}
function audioStatus(status) {
  const wasConnected = connection === 'connected';
  connection = status.connection;
  if (wasConnected && connection !== 'connected') {
    if (pendingKey) invalidatedProposals.add(pendingKey);
    acknowledgedKey = ''; proposalGeneration++;
    // Incomplete voice fragments must not be carried into a new connection owner.
    for (const [key, turn] of liveTurns) if (!turn.final) liveTurns.delete(key);
    renderMessages(); renderProposal();
  }
  text('#connection-label', { connected:'Notebook connected',connecting:'Connecting notebook',reconnecting:'Reconnecting notebook',offline:'Notebook paused' }[connection]);
  $('#connection-dot').classList.toggle('online', connection === 'connected');
  text('#mic-state', status.muted && status.voiceOn ? 'Mic muted' : {off:'Mic off',requesting:'Mic permission',ready:'Mic ready',denied:'Mic blocked',error:'Mic unavailable'}[status.mic] || 'Mic off');
  text('#provider-state', { off:'Voice off',unavailable:'Voice unavailable',connecting:'Voice connecting',connected:'Voice ready',listening:'Voice listening',speaking:'Voice responding',reconnecting:'Voice reconnecting',muted:'Voice muted' }[status.provider] || 'Voice waiting');
  text('#playback-state', { idle:'Speaker idle',queued:'Speaker queued',playing:'Speaker playing',error:'Speaker unavailable' }[status.playback]);
  const title = connection !== 'connected' ? connection === 'reconnecting' ? 'Reconnecting your notebook…' : 'Your notebook is reconnecting.' : status.muted && status.voiceOn ? 'Muted. Take your time.' : status.playback === 'playing' ? 'Your companion is speaking.' : status.voiceOn ? status.provider === 'listening' ? 'Listening. Follow your curiosity.' : 'Connecting your voice…' : status.mic === 'denied' ? 'Your microphone needs permission.' : status.provider === 'unavailable' ? 'Keep exploring with text.' : 'Your companion, a tap away.';
  text('#voice-title', title);
  text('#voice-detail', status.detail || (status.voiceOn ? 'Ask, predict, or change your mind.' : 'Voice is optional. Your notebook is always here.'));
  text('#mute', status.muted ? 'Unmute' : 'Mute');
  $('#mute').hidden = !status.voiceOn;
  $('#mute').setAttribute('aria-pressed', String(status.muted));
  $('#voice-end').hidden = !status.voiceOn;
  $('#interrupt').hidden = !['queued','playing'].includes(status.playback);
  $('#voice-toggle').disabled = status.mic === 'requesting' || connection !== 'connected';
  $('#voice-toggle').setAttribute('aria-label', status.voiceOn ? status.muted ? 'Unmute voice' : 'Mute voice' : status.mic === 'denied' ? 'Retry microphone' : 'Start voice');
  $('#voice-request').disabled = $('#voice-toggle').disabled;
  text('#voice-request', status.voiceOn ? status.muted ? 'Unmute microphone' : 'Mute microphone' : 'Speak a request');
  $('.voice-dock').dataset.voiceOn = String(status.voiceOn);
  $('.voice-dock').dataset.speaking = String(status.playback === 'playing');
  controls();
  if (connection === 'connected') schedulePresentation();
}

$('#pairing').addEventListener('submit', event => { event.preventDefault(); boot($('#pairing-code').value.trim()); });
$('#dismiss-notice').onclick = () => { $('#notice').hidden = true; };
$('#reconnect').onclick = async () => {
  if (!api.sessionId) return boot();
  await resync(); client?.reconnect();
};
$('#conditions').addEventListener('click', event => {
  const button = event.target.closest('[data-condition]');
  if (button) void act('condition', { condition_id: button.dataset.condition });
});
$('#prediction').oninput = () => { $('#prediction').dataset.dirty = 'true'; };
$('#prediction-form').onsubmit = async event => {
  event.preventDefault(); const value = $('#prediction').value.trim(); if (!value) return;
  await act('prediction', { text: value }, () => { delete $('#prediction').dataset.dirty; });
};
$('#message-form').onsubmit = async event => {
  event.preventDefault(); const value = $('#message').value.trim(); if (!value) return;
  await act('request', { text: value, client_request_id: crypto.randomUUID() }, () => { $('#message').value = ''; });
};
$('#message').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('#message-form').requestSubmit(); } };
$('#answer-clarification').onclick = () => $('#message').focus();
$('#confirm').onclick = () => {
  if ($('#confirm').disabled) return;
  const proposal = snapshot.pending;
  act('confirm', {request_id:proposal.request_id,proposal_version:proposal.proposal_version});
};
$('#cancel').onclick = () => act('cancel', {request_id:snapshot.pending?.request_id});
$('#review-again').onclick = () => { attemptedPresentations.delete(pendingKey); schedulePresentation(true); };
$('#reflection-form').onsubmit = event => {
  event.preventDefault(); const value = $('#reflection').value.trim(); if (value) act('reflection', {text:value}, () => { text('#reflection-saved','Reflection saved.'); $('#reflection').value = ''; });
};
$('#new-trial').onclick = async () => {
  const prepared = await act('prepare', {}, () => {
    $('#prediction').value = '';
    delete $('#prediction').dataset.dirty;
    $('#reflection').value = '';
    text('#reflection-saved', '');
    $('#reflection-panel').open = false;
    render();
  });
  if (prepared) {
    $('#message').focus({ preventScroll: true });
    $('#workspace').scrollIntoView({ block: 'start' });
  }
};
async function stop() {
  if (pendingKey) invalidatedProposals.add(pendingKey);
  acknowledgedKey = '';
  proposalGeneration++;
  if (snapshot) { renderProposal(); controls(); }
  if (client?.stopTrial()) return;
  if (!api.sessionId) return;
  try { client?.acceptState(await api.action('stop')); notify('Stop requested. Your notebook is preserved.'); } catch (error) { fail(error); }
}
$('#stop').onclick = stop;
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !event.isComposing) stop(); });
function toggleVoice() {
  if (!client) return;
  if (client.status.voiceOn) client.setMuted(!client.status.muted); else client.startVoice();
}
$('#voice-toggle').onclick = toggleVoice;
$('#voice-request').onclick = toggleVoice;
$('#mute').onclick = () => client?.setMuted(!client.status.muted);
$('#voice-end').onclick = () => client?.stopVoice();
$('#interrupt').onclick = () => client?.interrupt();
// Scrolling or returning to a foreground tab can make a proposal truly visible.
window.addEventListener('scroll', () => schedulePresentation(), { passive:true });
window.addEventListener('resize', () => schedulePresentation(), { passive:true });
window.visualViewport?.addEventListener('resize', () => schedulePresentation(), { passive: true });
document.addEventListener('visibilitychange', () => { if (!document.hidden) schedulePresentation(); });
setInterval(() => { controls(); if (snapshot?.pending && expired(snapshot.pending)) text('#proposal-status','This proposal has expired. Send a new request.'); }, 1000);
window.addEventListener('pagehide', () => { releaseScene(); client?.close(); });
window.addEventListener('pageshow', event => { if (event.persisted) boot(); });
boot();
