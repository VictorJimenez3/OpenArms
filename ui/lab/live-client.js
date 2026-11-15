const noop = () => {};
const id = () => crypto.randomUUID();
function encode(buffer) {
  const bytes = new Uint8Array(buffer);
  let string = '';
  for (let i = 0; i < bytes.length; i += 4096) string += String.fromCharCode(...bytes.subarray(i, i + 4096));
  return btoa(string);
}

// A reply is audible only after scheduled PCM finishes. reply_end is not playback.
export class PcmPlayer {
  constructor(context, send, change = noop) {
    this.context = context;
    this.send = send;
    this.change = change;
    this.replies = new Map();
    this.sources = new Set();
    this.nextTime = 0;
    this.timer = null;
  }
  start(replyId) {
    if (!replyId || this.replies.has(replyId)) return;
    this.replies.set(replyId, { id: replyId, count: 0, samples: 0, ended: false, aborted: false, acked: false });
    // Keep a bounded tombstone set so interrupted/duplicate chunks cannot revive a reply.
    if (this.replies.size > 250) this.replies.delete(this.replies.keys().next().value);
  }
  chunk(replyId, data) {
    const reply = this.replies.get(replyId);
    if (!reply || reply.aborted || reply.ended || reply.acked) return;
    if (this.context.state !== 'running') { this.fail(replyId, 'Speaker paused. Tap Start voice to restore audio.'); return; }
    try {
      const binary = atob(data);
      if (!binary.length || binary.length % 2 || binary.length > 24000 * 2 * 12) throw new Error('Invalid audio frame');
      if (this.nextTime - this.context.currentTime > 12) throw new Error('Speech queue exceeded its limit');
      const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
      const view = new DataView(bytes.buffer);
      const pcm = new Float32Array(bytes.length / 2);
      for (let n = 0; n < pcm.length; n++) pcm[n] = view.getInt16(n * 2, true) / 32768;
      const buffer = this.context.createBuffer(1, pcm.length, 24000);
      buffer.copyToChannel(pcm, 0);
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.context.destination);
      const start = Math.max(this.context.currentTime + 0.015, this.nextTime);
      this.nextTime = start + buffer.duration;
      reply.count++;
      reply.samples += pcm.length;
      const entry = { source, replyId, start };
      this.sources.add(entry);
      source.onended = () => {
        this.sources.delete(entry);
        source.disconnect();
        reply.count--;
        this.maybeAck(reply);
        this.report();
      };
      source.start(start);
      this.report();
    } catch { this.fail(replyId, 'Speaker playback failed. Your text conversation is still available.'); }
  }
  end(replyId) { const reply = this.replies.get(replyId); if (reply) { reply.ended = true; this.maybeAck(reply); } }
  maybeAck(reply) {
    if (reply.ended && reply.samples > 0 && reply.count === 0 && !reply.aborted && !reply.acked) {
      reply.acked = true;
      this.send({ type: 'played', reply_id: reply.id });
    }
  }
  fail(replyId, message) { this.clear(replyId, true); this.change('error', message); }
  clear(replyId, notify = false) {
    const affected = new Set();
    for (const reply of this.replies.values()) {
      if ((!replyId || reply.id === replyId) && !reply.acked && !reply.aborted) { reply.aborted = true; affected.add(reply.id); }
    }
    for (const entry of [...this.sources]) {
      if (!replyId || entry.replyId === replyId) {
        entry.source.onended = null;
        try { entry.source.stop(); entry.source.disconnect(); } catch {}
        this.sources.delete(entry);
      }
    }
    if (!this.sources.size) this.nextTime = this.context.currentTime;
    if (notify) for (const reply of affected) this.send({ type: 'interrupt', reply_id: reply });
    this.report();
  }
  report() {
    clearTimeout(this.timer);
    const now = this.context.currentTime;
    const firstStart = Math.min(...[...this.sources].map(entry => entry.start));
    const playing = firstStart <= now;
    this.change(this.sources.size ? playing ? 'playing' : 'queued' : 'idle');
    if (!playing && this.sources.size) this.timer = setTimeout(() => this.report(), (firstStart - now) * 1000 + 5);
  }
}

export class SessionClient {
  #api;
  constructor(api, options = {}) {
    this.#api = api;
    this.onState = options.onState || noop;
    this.onTranscript = options.onTranscript || noop;
    this.onInterrupted = options.onInterrupted || noop;
    this.onStatus = options.onStatus || noop;
    this.onError = options.onError || noop;
    this.onResync = options.onResync || noop;
    this.status = { connection: 'connecting', mic: 'off', provider: 'off', playback: 'idle', muted: false, voiceOn: false, detail: '' };
    this.ws = null;
    this.ready = false;
    this.closed = false;
    this.retry = 0;
    this.revision = -1;
    this.generation = null;
    this.audioEpoch = 0;
    this.startEpoch = 0;
    this.context = null;
    this.player = null;
    this.captureEnabled = false;
    this.heartbeat = null;
    this.retryTimer = null;
    this.watchdog = null;
    this.routeHandler = () => { if (this.status.voiceOn) this.pauseAudio('Audio route changed. Tap Start voice to reconnect your microphone.'); };
    this.visibilityHandler = () => { if (document.hidden && this.status.voiceOn) this.pauseAudio('Voice paused while the page was in the background. Tap Start voice to resume.'); };
    navigator.mediaDevices?.addEventListener('devicechange', this.routeHandler);
    document.addEventListener('visibilitychange', this.visibilityHandler);
  }
  update(patch) { Object.assign(this.status, patch); this.gate(); this.onStatus({ ...this.status }); }
  send(frame) {
    // No send queue: controls/audio are never replayed after reconnection.
    if (!this.ready || this.ws?.readyState !== WebSocket.OPEN || this.ws.bufferedAmount > 128000) return false;
    this.ws.send(JSON.stringify(frame));
    return true;
  }
  connect() {
    if (this.ws && [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.ws.readyState)) return;
    this.closed = false;
    clearTimeout(this.retryTimer);
    this.ready = false;
    this.update({ connection: this.retry ? 'reconnecting' : 'connecting' });
    const url = new URL(`/api/sessions/${encodeURIComponent(this.#api.sessionId)}/live`, location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(url);
    this.ws = socket;
    const connectionId = id();
    let lastPong = Date.now();
    let helloTime = 0;
    const sentPings = new Set();
    let seq = 0;
    this.watchdog = setInterval(() => {
      if (this.ws === socket && Date.now() - lastPong > 15000) socket.close(4000, 'Heartbeat timeout');
    }, 1000);
    socket.onopen = () => {
      if (this.ws !== socket) return;
      socket.send(JSON.stringify({ type: 'hello', protocol_version: 1, connection_id: connectionId, access_token: this.#api.accessToken }));
    };
    socket.onmessage = ({ data }) => {
      if (this.ws !== socket) return;
      let frame;
      try { frame = JSON.parse(data); } catch { return; }
      if (frame.type === 'hello') {
        if (this.ready || frame.protocol_version !== 1 || frame.connection_id !== connectionId || !Number.isSafeInteger(frame.generation) || frame.generation < 0) {
          this.closed = true; socket.close(1002, 'Invalid session greeting'); this.onError('The lab protocol did not match this browser. Reload after updating the app.'); return;
        }
        if (this.generation === null || frame.generation > this.generation) this.setGeneration(frame.generation);
        this.ready = true;
        helloTime = Date.now(); lastPong = helloTime;
        this.update({ connection: 'connected' });
        clearInterval(this.heartbeat);
        this.heartbeat = setInterval(() => {
          const current = ++seq;
          if (this.send({ type: 'ping', seq: current })) sentPings.add(current);
        }, 5000);
        this.onResync();
        return;
      }
      if (!this.ready) return;
      if (frame.type === 'pong') {
        if (sentPings.delete(frame.seq)) { lastPong = Date.now(); if (lastPong - helloTime >= 15000) this.retry = 0; }
        return;
      }
      this.receive(frame);
    };
    socket.onerror = noop; // onclose owns retry and cleanup.
    socket.onclose = event => {
      if (this.ws !== socket) return;
      this.ws = null; this.ready = false;
      clearInterval(this.heartbeat); clearInterval(this.watchdog);
      this.dropAudio();
      this.update({ voiceOn: false, mic: 'off', provider: 'off', playback: 'idle' });
      if ([1008, 4001, 4003, 4009, 4401, 4403, 4409].includes(event.code)) this.closed = true;
      if (this.closed || this.retry >= 6) {
        this.update({ connection: 'offline', detail: event.code === 1008 || event.code === 4401 ? 'Session access ended. Reconnect your session.' : 'Session paused. Reconnect to restore the notebook.' });
        return;
      }
      this.retry++;
      this.update({ connection: 'reconnecting', detail: 'Reconnecting your notebook. Voice will need a fresh tap.' });
      this.retryTimer = setTimeout(() => this.connect(), Math.min(8000, 500 * 2 ** (this.retry - 1)));
    };
  }
  receive(frame) {
    switch (frame.type) {
      case 'state': this.acceptState(frame.state); break;
      case 'transcript': if (frame.turn_id && ['user','assistant'].includes(frame.role) && typeof frame.text === 'string') this.onTranscript(frame); break;
      case 'status': {
        // Optional relay metadata is diagnostic only. The audio gate uses provider status.
        if (typeof frame.model === 'string') this.status.model = frame.model;
        if (typeof frame.provider === 'string') this.status.providerName = frame.provider;
        if (frame.status === 'unavailable') {
          this.dropAudio();
          this.update({ voiceOn: false, provider: 'unavailable', mic: 'off', playback: 'idle', detail: frame.message || 'Voice is unavailable. You can keep exploring with text.' });
        } else if (this.status.voiceOn) {
          this.update({ provider: frame.status, detail: frame.message || '' });
          if (frame.status === 'reconnecting') this.player?.clear();
        }
        break;
      }
      case 'reply_start': if (this.status.voiceOn && !this.status.muted) this.player?.start(frame.reply_id); break;
      case 'audio': if (this.status.voiceOn && !this.status.muted) this.player?.chunk(frame.reply_id, frame.data); break;
      case 'reply_end': this.player?.end(frame.reply_id); break;
      case 'interrupted':
        this.player?.clear(frame.reply_id); this.onInterrupted(frame.reply_id); this.resetCapture(); break;
      case 'error':
        if (['owner_replaced','connection_replaced','session_replaced','unauthorized'].includes(frame.code)) { this.closed = true; this.ws?.close(); }
        this.onError(frame.message || 'Voice hit a problem. Your text notebook is still available.');
        break;
    }
  }
  acceptState(state) {
    if (state?.session_id !== this.#api.sessionId || !Number.isSafeInteger(state.revision) || state.revision <= this.revision ||
        !Number.isSafeInteger(state.generation) || state.generation < 0 || state.generation < this.generation) return false;
    this.revision = state.revision;
    this.setGeneration(state.generation);
    this.onState(state);
    return true;
  }
  setGeneration(generation) {
    if (generation === this.generation) return;
    this.generation = generation;
    this.resetCapture();
    this.player?.clear();
  }
  gate() {
    const enabled = Boolean(this.ready && this.status.voiceOn && !this.status.muted && this.status.mic === 'ready' && ['connected','listening','speaking'].includes(this.status.provider));
    if (enabled !== this.captureEnabled) {
      this.captureEnabled = enabled;
      this.audioEpoch++;
      this.worklet?.port.postMessage({ type: 'gate', enabled, epoch: this.audioEpoch });
    }
  }
  resetCapture() {
    this.audioEpoch++;
    this.worklet?.port.postMessage({ type: 'gate', enabled: this.captureEnabled, epoch: this.audioEpoch });
  }
  async startVoice() {
    if (this.status.voiceOn || this.status.mic === 'requesting') return;
    if (!this.ready) { this.onError('Your notebook is reconnecting. Try voice once it is connected.'); return; }
    const epoch = ++this.startEpoch;
    this.update({ mic: 'requesting', provider: 'off', detail: 'Allow microphone access to talk. Text works without it.' });
    try {
      if (!isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Voice needs HTTPS or localhost. Continue with text, or open the trusted lab link.');
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error('This browser does not support streaming audio. Continue with text.');
      // Create/resume before awaiting permissions: iOS needs the original user gesture.
      this.context ||= new Audio();
      await this.context.resume();
      if (epoch !== this.startEpoch) return;
      if (this.context.state !== 'running') throw new Error('Speaker is paused. Tap Start voice again to enable sound.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (epoch !== this.startEpoch) { stream.getTracks().forEach(track => track.stop()); return; }
      this.stream = stream;
      await this.context.audioWorklet.addModule(new URL('./audio-worklet.js', import.meta.url));
      if (epoch !== this.startEpoch) return;
      this.source = this.context.createMediaStreamSource(stream);
      this.worklet = new AudioWorkletNode(this.context, 'pcm-capture-processor');
      this.silent = this.context.createGain();
      this.silent.gain.value = 0;
      this.source.connect(this.worklet); this.worklet.connect(this.silent); this.silent.connect(this.context.destination);
      this.worklet.port.onmessage = ({ data }) => {
        if (data.type === 'pcm' && data.epoch === this.audioEpoch && this.captureEnabled) this.send({ type: 'audio', data: encode(data.buffer), epoch: this.generation });
      };
      this.player = new PcmPlayer(this.context, frame => {
        if (frame.type === 'interrupt') this.onInterrupted(frame.reply_id);
        this.send(frame);
      }, (playback, detail) => this.update({ playback, ...(detail ? { detail } : {}) }));
      stream.getAudioTracks().forEach(track => { track.onended = () => this.pauseAudio('Microphone disconnected. Check your input and tap Start voice.'); });
      this.context.onstatechange = () => {
        if (this.context?.state !== 'running' && this.status.voiceOn) this.pauseAudio('Audio paused by your device. Tap Start voice to resume.');
      };
      if (!this.send({ type: 'start_voice' })) throw new Error('Voice could not start while the connection changed. Try again.');
      this.update({ voiceOn: true, muted: false, mic: 'ready', provider: 'connecting', playback: 'idle', detail: 'Connecting the voice companion…' });
    } catch (error) {
      if (epoch !== this.startEpoch) return;
      const denied = ['NotAllowedError','PermissionDeniedError'].includes(error.name);
      this.dropAudio();
      this.update({ voiceOn: false, mic: denied ? 'denied' : 'error', provider: 'off', playback: 'idle', detail: denied ? 'Microphone blocked. Allow it in browser site settings, then tap Retry microphone. Text is ready.' : error.message });
    }
  }
  dropAudio() {
    ++this.startEpoch;
    this.captureEnabled = false; this.resetCapture();
    this.player?.clear(undefined, false); this.player = null;
    this.onInterrupted();
    this.stream?.getTracks().forEach(track => { track.onended = null; track.stop(); }); this.stream = null;
    this.source?.disconnect(); this.worklet?.disconnect(); this.silent?.disconnect();
    if (this.worklet) this.worklet.port.onmessage = null;
    this.source = this.worklet = this.silent = null;
    if (this.context) { this.context.onstatechange = null; this.context.close().catch(noop); this.context = null; }
  }
  pauseAudio(detail) {
    this.player?.clear(undefined, true);
    this.send({ type: 'stop_voice' });
    this.dropAudio();
    this.update({ voiceOn: false, mic: 'off', provider: 'off', playback: 'idle', detail });
  }
  stopVoice() { this.pauseAudio('Voice ended. Your conversation and notebook are saved.'); }
  setMuted(muted) {
    if (!this.status.voiceOn) return;
    this.player?.clear(undefined, true);
    this.stream?.getAudioTracks().forEach(track => { track.enabled = !muted; });
    this.update({ muted: Boolean(muted), playback: 'idle', detail: muted ? 'Microphone muted. Queued speech cleared.' : '' });
    this.resetCapture();
    if (!this.send({ type: 'mute', muted: Boolean(muted) })) this.pauseAudio('Connection changed. Tap Start voice after reconnecting.');
  }
  interrupt() { this.player?.clear(undefined, true); this.resetCapture(); this.update({ playback: 'idle' }); }
  stopTrial() { this.interrupt(); return this.send({ type: 'stop' }); }
  reconnect() { this.retry = 0; this.closed = false; this.connect(); }
  close() {
    this.closed = true; clearTimeout(this.retryTimer); clearInterval(this.heartbeat); clearInterval(this.watchdog);
    this.send({ type: 'close' }); this.ready = false;
    this.dropAudio();
    const socket = this.ws; this.ws = null; socket?.close();
    navigator.mediaDevices?.removeEventListener('devicechange', this.routeHandler);
    document.removeEventListener('visibilitychange', this.visibilityHandler);
  }
}
