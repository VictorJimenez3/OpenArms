// Credentials stay in this client and per-tab sessionStorage; never in a URL or view.
export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}
export class LabApiClient {
  #credentials = null;
  constructor() {
    try { this.#credentials = JSON.parse(sessionStorage.getItem('openarms.ph.session')); } catch { /* Private browsing can disable storage. */ }
  }
  get sessionId() { return this.#credentials?.session_id; }
  get accessToken() { return this.#credentials?.access_token; }
  forget() { this.#credentials = null; try { sessionStorage.removeItem('openarms.ph.session'); } catch {} }
  async request(path, body, token = this.accessToken) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    let response;
    try {
      response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers: { Accept: 'application/json', ...(body === undefined ? {} : {'Content-Type':'application/json'}), ...(token ? { Authorization: `Bearer ${token}` } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal, cache: 'no-store', credentials: 'same-origin' });
    } catch { throw new ApiError('We couldn’t reach the lab. Your draft is still here. Reconnect, then check the notebook before trying again.', 0); }
    finally { clearTimeout(timeout); }
    let data;
    try { data = await response.json(); } catch { throw new ApiError('The lab sent an unreadable response. Reconnect to check your notebook.', response.status); }
    if (!response.ok) throw new ApiError(typeof data.detail === 'string' ? data.detail : typeof data.message === 'string' ? data.message : `The lab couldn’t complete that request (${response.status}).`, response.status);
    return data;
  }
  async create(pairingCode) {
    const result = await this.request('/api/sessions', {}, pairingCode || null);
    if (!result.session_id || !result.access_token) throw new ApiError('The lab did not provide a session credential.', 502);
    this.#credentials = { session_id: result.session_id, access_token: result.access_token };
    try { sessionStorage.setItem('openarms.ph.session', JSON.stringify(this.#credentials)); } catch {}
    // The token must never reach a renderer or a transcript.
    const { access_token, ...snapshot } = result;
    return snapshot;
  }
  snapshot() { return this.request(`/api/sessions/${encodeURIComponent(this.sessionId)}`); }
  action(name, body = {}) { return this.request(`/api/sessions/${encodeURIComponent(this.sessionId)}/${name}`, body); }
}
