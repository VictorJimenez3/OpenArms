// Connects the student app to the OpenArms lab server when it is serving this page.
// The server owns planning, exact proposals, consent, execution and observation;
// this client only relays the student's words and choices. Without a server the
// app falls back to recorded simulations.
const KEY = 'openarms.student.session';
let creds = null;
try { creds = JSON.parse(sessionStorage.getItem(KEY)); } catch { /* Storage can be unavailable. */ }

async function http(path, body, token = creds?.access_token) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST', cache: 'no-store', signal: AbortSignal.timeout(20000),
    headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : `The lab server said no (${response.status}).`), { status: response.status });
  return data;
}

export const Live = {
  variant: null,
  expert: null,
  online: false,
  voice: false,
  async init() {
    if (!location.protocol.startsWith('http')) return;
    try {
      const health = await http('/api/health', undefined, null);
      if (health.backend !== 'mujoco' || health.hardware_enabled || health.pairing_required) return;
      this.expert = health.expert?.model || health.expert_model || null;
      this.voice = Boolean(health.live_configured);
      const state = creds ? await this.state().catch(() => null) : null;
      this.variant = (state || await this.open()).experiment?.variant || null;
      this.online = true;
    } catch { this.variant = null; }
  },
  async open() {
    const { access_token, ...state } = await http('/api/sessions', {}, null);
    creds = { session_id: state.session_id, access_token };
    try { sessionStorage.setItem(KEY, JSON.stringify(creds)); } catch { /* Keep it in memory. */ }
    return state;
  },
  path(name = '') { return `/api/sessions/${encodeURIComponent(creds.session_id)}${name && '/' + name}`; },
  async call(name, body) {
    try { return await http(this.path(name), body); }
    catch (error) {
      if (error.status !== 401 && error.status !== 404) throw error;
      await this.open();
      return http(this.path(name), body);
    }
  },
  state() { return http(this.path()); },
  // The bench keeps its state between commands. Start a lab on a full beaker; reset only when asked.
  async fresh() {
    const state = await this.call();
    const used = state.pending || (state.state?.pours_done || 0) > 0 || state.state?.at !== 'HOME' || (state.tasks || []).some(t => ['queued', 'running', 'executing'].includes(t.status));
    return used ? this.reset() : state;
  },
  reset() { return this.call('prepare', {}); },
  ask(text) { return this.call('request', { text, client_request_id: `student-${Date.now()}` }); },
  present(p) { return this.call('present', { request_id: p.request_id, proposal_version: p.proposal_version, channel: 'text' }); },
  confirm(p) { return this.call('confirm', { request_id: p.request_id, proposal_version: p.proposal_version }); },
  cancel(p) { return this.call('cancel', p ? { request_id: p.request_id } : {}); },
  stop() { return this.call('stop', {}); },
  // Ask Ollie: conversation only. Returns null when the server has no chat model, so the app can fall back.
  async chat(question, context, history) {
    if (!this.online) return null;
    try { return (await this.call('ollie', { question: question.slice(0, 300), context: context.slice(0, 2500), history: history.slice(-6) })).answer || null; }
    catch { return null; }
  },
  // Spoken conversation over the lab's existing Gemini Live channel, reusing the bench site's client.
  async voiceClient(handlers) {
    const { SessionClient } = await import('/live-client.js');
    const client = new SessionClient({ get sessionId() { return creds.session_id; }, get accessToken() { return creds.access_token; } }, handlers);
    client.connect();
    return client;
  },
  async blob(url) {
    const response = await fetch(new URL(url, location.origin).pathname, { headers: { Authorization: `Bearer ${creds.access_token}` }, cache: 'no-store' });
    if (!response.ok) throw new Error('Picture unavailable');
    return response.blob();
  },
};

// Small JPEG copy of a camera frame, so a report can keep its evidence picture.
export async function thumbnail(blob, width = 480) {
  const bitmap = await createImageBitmap(blob);
  const canvas = Object.assign(document.createElement('canvas'), { width, height: Math.round(width * bitmap.height / bitmap.width) });
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.72);
}
