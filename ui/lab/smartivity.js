const STATUS = {
  idle: 'Ready',
  running: 'Running',
  success: 'Completed',
  failed: 'Run failed',
  stopped: 'Stopped',
};
const COMMAND_STATUS = { start: 'Starting simulation', reset: 'Resetting scene', stop: 'Stopping simulation' };
const clock = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' });

function put(node, value) {
  const text = typeof value === 'string' ? value : '';
  if (node.textContent !== text) node.textContent = text;
}

export class SmartivityView {
  constructor(api) {
    this.api = api;
    this.panel = document.querySelector('#smartivity');
    const byId = id => this.panel.querySelector('#smartivity-' + id);
    this.status = byId('status');
    this.objective = byId('objective');
    this.evidence = byId('evidence');
    this.observations = byId('observations');
    this.rows = ['action', 'outcome', 'recovery'].map(name => [name, byId(name), byId(name + '-row')]);
    this.controls = byId('controls');
    this.seed = byId('seed');
    this.start = byId('start');
    this.reset = byId('reset');
    this.stop = byId('stop');
    this.cameras = Object.fromEntries(['overview', 'side'].map(name => {
      const figure = this.panel.querySelector(`[data-camera="${name}"]`);
      return [name, {
        image: figure.querySelector('img'),
        empty: figure.querySelector('.smartivity-image p'),
        time: figure.querySelector('time'),
      }];
    }));
    this.controls.addEventListener('submit', event => {
      event.preventDefault();
      void this.command('start');
    });
    this.reset.addEventListener('click', () => this.command('reset'));
    this.stop.addEventListener('click', () => this.command('stop'));
  }

  setSession(id) {
    if ((this.episode?.id ?? null) === id) return;
    clearTimeout(this.timer);
    this.episode?.controller.abort();
    this.panel.hidden = true;
    this.clearCameras();
    this.episode = id ? { id, controller: new AbortController(), version: 0, pending: new Set() } : null;
    if (this.episode) void this.enable(this.episode);
  }

  async enable(episode) {
    let health;
    try { health = await this.api.request('/api/health', undefined, null); }
    catch { return; }
    if (episode !== this.episode || health.smartivity_available !== true) return;
    this.render(episode);
    this.panel.hidden = false;
    void this.poll(episode);
  }

  async poll(episode) {
    const { id, version } = episode;
    const current = () => this.episode === episode && episode.version === version;
    try {
      if (document.hidden || episode.pending.size) return;
      const state = await this.api.request(`/api/sessions/${encodeURIComponent(id)}/smartivity`);
      if (!current()) return;
      if (!episode.state && Number.isSafeInteger(state.seed)) this.seed.value = state.seed;
      if (state.generation !== episode.state?.generation) this.clearCameras();
      episode.state = state;
      episode.connectionError = '';
      this.render(episode);
      await Promise.all(Object.entries(this.cameras).map(async ([name, camera]) => {
        const frame = state.frames?.[name];
        if (!frame || frame.frame_id === camera.id) return;
        const next = await this.api.smartivityFrame(name, episode.controller.signal).catch(() => null);
        if (!current() || !next || (next.generation !== null && Number(next.generation) !== state.generation)) return;
        await this.showFrame(camera, next, current);
      }));
    } catch {
      if (!current()) return;
      episode.connectionError = 'Simulation updates unavailable';
      this.render(episode);
    } finally {
      if (this.episode === episode) {
        this.timer = setTimeout(() => this.poll(episode), episode.state?.status === 'running' ? 400 : 1000);
      }
    }
  }

  async command(action) {
    const episode = this.episode;
    if (!episode?.state || episode.pending.has(action)) return;
    if (action !== 'stop' && (episode.pending.size || !this.controls.reportValidity())) return;
    const body = action === 'stop' ? {} : { seed: this.seed.valueAsNumber };
    episode.pending.add(action);
    episode.commandError = '';
    episode.version++;
    this.render(episode);
    try {
      await this.api.action('smartivity/' + action, body);
      if (this.episode === episode && action !== 'stop') this.clearCameras();
    } catch (error) {
      episode.commandError = error.message || 'The simulation did not accept the request.';
    } finally {
      episode.pending.delete(action);
      if (this.episode === episode) this.render(episode);
    }
  }

  render(episode) {
    const { state, pending } = episode;
    const action = Array.from(pending).at(-1);
    const progress = state?.status === 'running' && typeof state.phase === 'string' ? ' — ' + state.phase.replaceAll('_', ' ') : '';
    const status = (STATUS[state?.status] || 'Connecting to simulation') + progress;
    put(this.status, COMMAND_STATUS[action] || episode.commandError || episode.connectionError || status);
    put(this.objective, state?.objective || 'Pour from the prepared beaker into the flask and observe the result.');
    for (const [name, field, row] of this.rows) {
      put(field, state?.[name]);
      row.hidden = field.textContent === '';
    }
    const entries = Array.isArray(state?.evidence) ? state.evidence.filter(item => typeof item === 'string') : [];
    const signature = JSON.stringify(entries);
    if (this.evidence.dataset.signature !== signature) {
      this.evidence.dataset.signature = signature;
      this.evidence.replaceChildren(...entries.map(item => {
        const li = document.createElement('li');
        put(li, item);
        return li;
      }));
    }
    this.observations.hidden = entries.length === 0;
    this.seed.disabled = pending.size > 0;
    this.start.disabled = !state || state.status === 'running' || pending.size > 0;
    this.reset.disabled = !state || pending.size > 0;
    this.stop.disabled = pending.has('stop') || (state?.status !== 'running' && !pending.has('start'));
  }

  async showFrame(camera, frame, current) {
    const url = URL.createObjectURL(frame.blob);
    const incoming = new Image();
    incoming.src = url;
    try { await incoming.decode(); }
    catch { URL.revokeObjectURL(url); return; }
    if (!current()) {
      URL.revokeObjectURL(url);
      return;
    }
    const previous = camera.image.getAttribute('src');
    camera.image.src = url;
    camera.image.hidden = false;
    camera.empty.hidden = true;
    camera.id = frame.id;
    if (previous) URL.revokeObjectURL(previous);
    const date = new Date(Number(frame.capturedAt) * 1000);
    camera.time.hidden = !frame.capturedAt || Number.isNaN(date.getTime());
    if (!camera.time.hidden) {
      put(camera.time, clock.format(date));
      camera.time.dateTime = date.toISOString();
      camera.time.title = frame.id ? `Frame ${frame.id}` : 'Capture time';
    }
  }

  clearCameras() {
    for (const camera of Object.values(this.cameras)) {
      const url = camera.image.getAttribute('src');
      if (url) URL.revokeObjectURL(url);
      camera.image.removeAttribute('src');
      camera.image.hidden = camera.time.hidden = true;
      camera.empty.hidden = false;
      camera.id = null;
    }
  }
}
