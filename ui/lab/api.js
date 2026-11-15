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
  async evidenceImage(frame, signal) {
    if (typeof frame.evidence_id !== 'string' || !frame.evidence_id) throw new Error('Image unavailable');
    return this.#media(frame.artifact_url, 'image', signal,
      path => path === `evidence/${encodeURIComponent(frame.evidence_id)}`);
  }
  async simulationMedia(artifactUrl, kind, signal) {
    const pathPattern = kind === 'video' ? /^media\/[0-9a-f]{32}\.mp4$/ : /^evidence\/[0-9a-f]{32}$/;
    return this.#media(artifactUrl, kind, signal, path => pathPattern.test(path));
  }
  async smartivityFrame(view, signal) {
    if (view !== 'overview' && view !== 'side') throw new Error('Unknown simulation camera');
    const path = `smartivity/frame/${view}`;
    const response = await this.#mediaResponse(
      `/api/sessions/${encodeURIComponent(this.sessionId)}/${path}`, 'image', signal, suffix => suffix === path
    );
    return {
      blob: await response.blob(),
      id: response.headers.get('X-Frame-Id'),
      capturedAt: response.headers.get('X-Captured-At'),
      generation: response.headers.get('X-Generation'),
    };
  }
  async #media(artifactUrl, kind, signal, acceptsPath) {
    return (await this.#mediaResponse(artifactUrl, kind, signal, acceptsPath)).blob();
  }
  async #mediaResponse(artifactUrl, kind, signal, acceptsPath) {
    const { session_id: sessionId, access_token: token } = this.#credentials || {};
    if (!sessionId || !token || typeof artifactUrl !== 'string') throw new Error('Media unavailable');
    const url = new URL(artifactUrl, location.href);
    const prefix = `/api/sessions/${encodeURIComponent(sessionId)}/`;
    if (url.origin !== location.origin || !/^https?:$/.test(url.protocol) || url.username || url.password ||
        url.search || url.hash || !url.pathname.startsWith(prefix) || !acceptsPath(url.pathname.slice(prefix.length))) {
      throw new Error('Media unavailable');
    }

    const video = kind === 'video';
    const response = await fetch(url.pathname, {
      headers: { Accept: video ? 'video/mp4' : 'image/*', Authorization: `Bearer ${token}` },
      signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]),
      redirect: 'error', cache: 'no-store', credentials: 'same-origin',
    });
    const type = response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase();
    if (!response.ok || !(video ? type === 'video/mp4' : /^image\/(png|jpeg|webp|gif|avif|bmp)$/.test(type))) {
      throw new Error('Media unavailable');
    }
    return response;
  }
}
