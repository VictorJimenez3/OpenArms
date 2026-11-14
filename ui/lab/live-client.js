/**
 * OpenArms Lab - Gemini Live WebSocket Client
 *
 * Implements real mic PCM capture via AudioWorklet (/audio-worklet.js),
 * speaker streaming queue with 24kHz PCM16 decoding,
 * interrupt cancellation & buffer flush,
 * echo cancellation, mute, lifecycle cleanup,
 * and bounded retry with fallback to deterministic text.
 */

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const len = bytes.byteLength;
  const chunkSize = 8192;
  for (let i = 0; i < len; i += chunkSize) {
    const chunk = bytes.subarray(i, Math.min(i + chunkSize, len));
    binary += String.fromCharCode.apply(null, chunk);
  }
  return btoa(binary);
}

function base64ToUint8Array(base64) {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

export class LiveClient {
  constructor(sessionId, options = {}) {
    this.sessionId = sessionId;
    this.baseUrl = options.baseUrl || '';

    // Callbacks
    this.onStatusChange = options.onStatusChange || (() => {});
    this.onTranscript = options.onTranscript || (() => {});
    this.onInterrupted = options.onInterrupted || (() => {});
    this.onError = options.onError || (() => {});
    this.onAudioLevel = options.onAudioLevel || (() => {});

    // State
    this.status = 'disconnected'; // disconnected, connecting, active, muted, unavailable, error
    this.isLiveAvailable = true;
    this.isMuted = false;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
    this.reconnectTimer = null;
    this.isUserInitiatedStop = false;

    // Web Audio graph
    this.audioCtx = null;
    this.mediaStream = null;
    this.sourceNode = null;
    this.workletNode = null;
    this.masterGainNode = null;

    // Speaker queue state
    this.activeSources = new Set();
    this.nextPlayTime = 0;
    this.generation = 0;
  }

  _buildWsUrl() {
    let host = window.location.host;
    let protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    if (this.baseUrl) {
      try {
        const parsed = new URL(this.baseUrl, window.location.href);
        host = parsed.host;
        protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
      } catch (e) {
        // fallback
      }
    }

    return `${protocol}//${host}/api/sessions/${encodeURIComponent(this.sessionId)}/live`;
  }

  async _initAudioContext() {
    if (!this.audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) {
        throw new Error('Web Audio API not supported in this browser');
      }
      this.audioCtx = new AudioContextClass();
      this.masterGainNode = this.audioCtx.createGain();
      this.masterGainNode.connect(this.audioCtx.destination);
    }

    if (this.audioCtx.state === 'suspended') {
      await this.audioCtx.resume();
    }
  }

  async _loadAudioWorklet() {
    // Try multiple possible paths to accommodate root or subpath mounts
    const workletPaths = [
      '/audio-worklet.js',
      './audio-worklet.js',
      'audio-worklet.js',
    ];

    let loaded = false;
    let lastErr = null;

    for (const path of workletPaths) {
      try {
        await this.audioCtx.audioWorklet.addModule(path);
        loaded = true;
        break;
      } catch (err) {
        lastErr = err;
      }
    }

    if (!loaded) {
      throw new Error(`Failed to load audio worklet module: ${lastErr?.message}`);
    }
  }

  async startVoice() {
    if (['connecting', 'reconnecting', 'active', 'muted'].includes(this.status)) return;
    const generation = ++this.generation;
    this.isUserInitiatedStop = false;
    this.isMuted = false;
    this.reconnectAttempts = 0;
    this._updateStatus('connecting', 'Requesting microphone and starting voice engine...');

    try {
      // 1. Initialize Audio Context (requires user gesture)
      await this._initAudioContext();
      if (generation !== this.generation) return;

      // 2. Request user microphone with echo cancellation
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (generation !== this.generation) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      this.mediaStream = stream;

      // 3. Load AudioWorklet
      await this._loadAudioWorklet();
      if (generation !== this.generation) return;

      // 4. Build audio processing pipeline
      this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
      this.workletNode = new AudioWorkletNode(this.audioCtx, 'pcm-capture-processor');

      // Wire worklet port to receive 16kHz PCM chunks
      this.workletNode.port.onmessage = (event) => {
        const msg = event.data;
        if (msg && msg.type === 'pcm' && msg.buffer) {
          this._handleMicPcmChunk(msg.buffer);
        }
      };

      this.sourceNode.connect(this.workletNode);
      // Connect worklet to a silent destination to keep the processor running in all browsers
      const dummyGain = this.audioCtx.createGain();
      dummyGain.gain.value = 0;
      this.workletNode.connect(dummyGain);
      dummyGain.connect(this.audioCtx.destination);

      // 5. Connect WebSocket
      this._connectWebSocket();
    } catch (err) {
      if (generation !== this.generation) return;
      console.error('[LiveClient] Voice initialization error:', err);
      this.cleanup();
      this._updateStatus('error', err.message || 'Microphone access denied or audio initialization failed');
      this.onError({ message: err.message });
      throw err;
    }
  }

  _connectWebSocket() {
    if (this.ws) {
      try { this.ws.close(); } catch (e) {}
    }

    const wsUrl = this._buildWsUrl();
    const socket = new WebSocket(wsUrl);
    this.ws = socket;

    this.ws.onopen = () => {
      if (this.ws !== socket) return;
      this.isLiveAvailable = true;
      this._updateStatus('connecting', 'Connecting to Gemini Live...');
    };

    this.ws.onmessage = (event) => {
      if (this.ws !== socket) return;
      this._handleServerMessage(event.data);
    };

    this.ws.onerror = (err) => {
      console.warn('[LiveClient] WebSocket error:', err);
    };

    this.ws.onclose = (event) => {
      if (this.ws !== socket) return;
      if (!this.isLiveAvailable || event.code === 1008) {
        this.cleanup();
        this._updateStatus('unavailable', 'Live voice unavailable. Use the text command field.');
        return;
      }
      if (!this.isUserInitiatedStop) {
        this._handleUnexpectedClose(event);
      } else {
        this._updateStatus('disconnected', 'Voice session closed');
      }
    };
  }

  _handleMicPcmChunk(buffer) {
    if (this.isMuted) return;

    // Calculate approximate RMS level for visualization
    const int16Array = new Int16Array(buffer);
    let sum = 0;
    for (let i = 0; i < int16Array.length; i += 4) {
      const val = int16Array[i] / 32768.0;
      sum += val * val;
    }
    const rms = Math.sqrt(sum / (int16Array.length / 4));
    this.onAudioLevel(rms);

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const base64Pcm = arrayBufferToBase64(buffer);
      this.ws.send(JSON.stringify({
        type: 'audio',
        data: base64Pcm,
      }));
    }
  }

  _handleServerMessage(rawData) {
    let msg;
    try {
      msg = JSON.parse(rawData);
    } catch (err) {
      console.warn('[LiveClient] Non-JSON message received:', err);
      return;
    }

    switch (msg.type) {
      case 'status':
        if (msg.status === 'unavailable') {
          this.isLiveAvailable = false;
          this._updateStatus('unavailable', msg.message || 'Live voice service unavailable on this host');
        } else {
          if (['connected','listening'].includes(msg.status)) this.reconnectAttempts = 0;
          const normalized = ['connected','listening'].includes(msg.status) ? (this.isMuted ? 'muted' : 'active') : msg.status;
          this._updateStatus(normalized, msg.message);
        }
        break;

      case 'audio':
        if (msg.data) {
          this._play24kPcmChunk(msg.data);
        }
        break;

      case 'transcript':
        if (msg.role && msg.text) {
          this.onTranscript({ role: msg.role, text: msg.text });
        }
        break;

      case 'interrupted':
        this._flushSpeakerQueue();
        this.onInterrupted();
        break;

      case 'error':
        this.onError({ message: msg.message || 'Unknown voice error' });
        break;

      default:
        break;
    }
  }

  _play24kPcmChunk(base64Data) {
    if (!this.audioCtx) return;

    try {
      // Bound queued speech during long responses or a stalled audio device.
      if (this.nextPlayTime - this.audioCtx.currentTime > 10) this._flushSpeakerQueue();
      const bytes = base64ToUint8Array(base64Data);
      const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
      const float32 = new Float32Array(int16.length);

      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
      }

      // 24kHz mono PCM
      const audioBuffer = this.audioCtx.createBuffer(1, float32.length, 24000);
      audioBuffer.copyToChannel(float32, 0);

      const now = this.audioCtx.currentTime;
      const startTime = Math.max(now, this.nextPlayTime);

      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.masterGainNode);

      source.start(startTime);
      this.nextPlayTime = startTime + audioBuffer.duration;
      this.activeSources.add(source);

      source.onended = () => {
        this.activeSources.delete(source);
      };
    } catch (err) {
      console.error('[LiveClient] Audio decoding/playback error:', err);
    }
  }

  _flushSpeakerQueue() {
    for (const source of this.activeSources) {
      try {
        source.stop(0);
      } catch (e) {
        // already stopped
      }
    }
    this.activeSources.clear();
    this.nextPlayTime = this.audioCtx ? this.audioCtx.currentTime : 0;
  }

  _handleUnexpectedClose(event) {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = 1000 * Math.pow(2, this.reconnectAttempts - 1);
      this._updateStatus('connecting', `Voice connection dropped. Reconnecting (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

      this.reconnectTimer = setTimeout(() => {
        if (!this.isUserInitiatedStop) {
          this._connectWebSocket();
        }
      }, delay);
    } else {
      this.cleanup();
      this.isLiveAvailable = false;
      this._updateStatus('unavailable', 'Live voice unavailable. Falling back to deterministic local text pathway.');
    }
  }

  _updateStatus(status, message = '') {
    this.status = status;
    this.onStatusChange({
      status,
      message,
      isLiveAvailable: this.isLiveAvailable,
      isMuted: this.isMuted,
    });
  }

  setMuted(muted) {
    this.isMuted = !!muted;
    this.mediaStream?.getAudioTracks().forEach(track => { track.enabled = !this.isMuted; });
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'mute', muted: this.isMuted });
    }
    if (this.status !== 'unavailable' && this.status !== 'disconnected' && this.status !== 'error') {
      this._updateStatus(this.isMuted ? 'muted' : 'active', this.isMuted ? 'Microphone muted' : 'Microphone active');
    }
  }

  sendText(text) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'text', text }));
      return true;
    }
    return false;
  }

  sendAudioEnd() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'audio_end' }));
    }
  }

  cleanup() {
    ++this.generation;
    this.isUserInitiatedStop = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this._flushSpeakerQueue();

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }

    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch (e) {}
      this.sourceNode = null;
    }

    if (this.workletNode) {
      try {
        this.workletNode.port.postMessage({ type: 'flush' });
        this.workletNode.disconnect();
      } catch (e) {}
      this.workletNode = null;
    }

    if (this.ws) {
      try {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: 'close' }));
        }
        this.ws.close();
      } catch (e) {}
      this.ws = null;
    }

    if (this.audioCtx) {
      this.audioCtx.close().catch(() => {});
      this.audioCtx = null;
      this.masterGainNode = null;
    }

    this._updateStatus('disconnected', 'Voice session stopped');
  }
}
