/**
 * OpenArms Lab - Main Application Controller
 *
 * Implements the student-directed accessible science lab interface.
 * Connects vanilla UI with REST API, Events WS, and Gemini Live Voice WS.
 * No build dependency. Standard ES Modules.
 */

import { LabApiClient, ApiError } from './api.js';
import { EventsClient } from './events-client.js';
import { LiveClient } from './live-client.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function epochDate(value) { return new Date(typeof value === 'number' ? value * 1000 : value); }

class OpenArmsApp {
  constructor() {
    this.api = new LabApiClient();
    this.sessionId = null;
    this.snapshot = null;
    this.health = null;
    this.experiments = [];
    this.skills = [];
    this.composedCandidate = null;

    // Clients
    this.eventsClient = null;
    this.liveClient = null;

    // Proposal countdown timer
    this.proposalCountdownInterval = null;

    // Bound DOM elements cache
    this.dom = {};
  }

  async init() {
    this._cacheDom();
    this._bindEvents();

    try {
      // 1. Fetch system health
      await this._loadHealth();

      // 2. Fetch available experiments
      await this._loadExperiments();

      // 3. Initialize or restore session
      await this._initSession();

      // 4. Load initial skills registry
      this._loadSkills().catch((e) => console.warn('Skills load error:', e));
    } catch (err) {
      console.error('Initialization error:', err);
      this._showToast(`Init error: ${err.message}`, true);
    }
  }

  _cacheDom() {
    this.dom = {
      // Header badges & controls
      badgeBackend: document.getElementById('badge-backend'),
      badgeBackendText: document.getElementById('badge-backend-text'),
      badgeVoice: document.getElementById('badge-voice'),
      badgeVoiceText: document.getElementById('badge-voice-text'),
      badgeConnection: document.getElementById('badge-connection'),
      badgeConnectionText: document.getElementById('badge-connection-text'),
      sessionIdDisplay: document.getElementById('session-id-display'),
      btnCopySession: document.getElementById('btn-copy-session'),
      btnNewSession: document.getElementById('btn-new-session'),
      btnHeaderStop: document.getElementById('btn-header-stop'),
      btnMobileStop: document.getElementById('btn-mobile-stop'),
      offlineBanner: document.getElementById('offline-banner'),
      offlineBannerText: document.getElementById('offline-banner-text'),
      btnRetryNetwork: document.getElementById('btn-retry-network'),

      // Proposal section
      proposalSection: document.getElementById('proposal-section'),
      proposalSummary: document.getElementById('proposal-summary'),
      proposalSkillId: document.getElementById('proposal-skill-id'),
      proposalParameters: document.getElementById('proposal-parameters'),
      proposalRequestId: document.getElementById('proposal-request-id'),
      proposalExpiresRow: document.getElementById('proposal-expires-row'),
      proposalExpiresVal: document.getElementById('proposal-expires-val'),
      btnConfirmProposal: document.getElementById('btn-confirm-proposal'),
      btnCancelProposal: document.getElementById('btn-cancel-proposal'),
      proposalCorrectForm: document.getElementById('proposal-correct-form'),
      proposalCorrectInput: document.getElementById('proposal-correct-input'),

      // Experiment Section
      experimentTitle: document.getElementById('experiment-title'),
      experimentQuestion: document.getElementById('experiment-question'),
      experimentInstructions: document.getElementById('experiment-instructions'),
      experimentIndepVar: document.getElementById('experiment-indep-var'),
      experimentControlledVars: document.getElementById('experiment-controlled-vars'),
      btnOpenExperiments: document.getElementById('btn-open-experiments'),
      experimentModal: document.getElementById('experiment-modal'),
      btnCloseExperimentModal: document.getElementById('btn-close-experiment-modal'),
      experimentsListContainer: document.getElementById('experiments-list-container'),

      // Prediction Section
      predictionSavedContainer: document.getElementById('prediction-saved-container'),
      predictionSavedDisplay: document.getElementById('prediction-saved-display'),
      btnEditPrediction: document.getElementById('btn-edit-prediction'),
      predictionForm: document.getElementById('prediction-form'),
      predictionInput: document.getElementById('prediction-input'),

      // Voice & Command Section
      btnToggleMic: document.getElementById('btn-toggle-mic'),
      btnMobileMic: document.getElementById('btn-mobile-mic'),
      micIcon: document.getElementById('mic-icon'),
      micPulseRing: document.getElementById('mic-pulse-ring'),
      voiceStatusText: document.getElementById('voice-status-text'),
      voiceHintText: document.getElementById('voice-hint-text'),
      audioLevelFill: document.getElementById('audio-level-fill'),
      btnToggleMute: document.getElementById('btn-toggle-mute'),
      muteIcon: document.getElementById('mute-icon'),
      muteText: document.getElementById('mute-text'),
      btnDisconnectVoice: document.getElementById('btn-disconnect-voice'),
      liveNoticeBox: document.getElementById('live-notice-box'),
      liveNoticeText: document.getElementById('live-notice-text'),
      liveFallbackBadge: document.getElementById('live-fallback-badge'),
      transcriptFeed: document.getElementById('transcript-feed'),
      commandForm: document.getElementById('command-form'),
      commandInput: document.getElementById('command-input'),

      // Bench & Arm State
      armStageTag: document.getElementById('arm-stage-tag'),
      stationAPod: document.getElementById('station-a-pod'),
      stationAContents: document.getElementById('station-a-contents'),
      stationAStatus: document.getElementById('station-a-status'),
      stationBPod: document.getElementById('station-b-pod'),
      stationBContents: document.getElementById('station-b-contents'),
      stationBStatus: document.getElementById('station-b-status'),
      armStatusVal: document.getElementById('arm-status-val'),
      armGripperVal: document.getElementById('arm-gripper-val'),
      armPositionVal: document.getElementById('arm-position-val'),
      armSafetyVal: document.getElementById('arm-safety-val'),

      // Observations Section
      observationsList: document.getElementById('observations-list'),
      observationsCount: document.getElementById('observations-count'),
      noObservationsMsg: document.getElementById('no-observations-msg'),

      // Quiz Section
      quizSection: document.getElementById('quiz-section'),
      quizPrompt: document.getElementById('quiz-prompt'),
      quizForm: document.getElementById('quiz-form'),
      quizOptionsContainer: document.getElementById('quiz-options-container'),
      quizFreeformContainer: document.getElementById('quiz-freeform-container'),
      quizFreeformInput: document.getElementById('quiz-freeform-input'),

      // Notebook & Messages
      notebookTimeline: document.getElementById('notebook-timeline'),
      noNotebookMsg: document.getElementById('no-notebook-msg'),
      btnExportNotebook: document.getElementById('btn-export-notebook'),
      messagesTimeline: document.getElementById('messages-timeline'),
      noMessagesMsg: document.getElementById('no-messages-msg'),

      // Developer Panel
      skillsTableBody: document.getElementById('skills-table-body'),
      btnRefreshSkills: document.getElementById('btn-refresh-skills'),
      skillComposeInput: document.getElementById('skill-compose-input'),
      btnComposeSkill: document.getElementById('btn-compose-skill'),
      composedCandidatePreview: document.getElementById('composed-candidate-preview'),
      candidateJsonPreview: document.getElementById('candidate-json-preview'),
      btnTestCandidate: document.getElementById('btn-test-candidate'),
      btnPromoteCandidate: document.getElementById('btn-promote-candidate'),
      snapshotInspector: document.getElementById('snapshot-inspector'),
    };
  }

  _bindEvents() {
    window.addEventListener('pagehide', () => this.liveClient?.cleanup());
    // Emergency STOP (Header, Mobile Bar, and Escape key)
    const handleStop = (e) => {
      e?.preventDefault();
      this._triggerEmergencyStop();
    };
    this.dom.btnHeaderStop.addEventListener('click', handleStop);
    this.dom.btnMobileStop.addEventListener('click', handleStop);
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        handleStop(e);
      }
    });

    // Copy Session ID
    this.dom.btnCopySession.addEventListener('click', async () => {
      if (this.sessionId) {
        try {
          await navigator.clipboard.writeText(this.sessionId);
          this._showToast(`Session ID copied: ${this.sessionId}`);
        } catch { this._showToast('Could not copy. Select the session ID in the header.', true); }
      }
    });

    // Reset / New Session
    this.dom.btnNewSession.addEventListener('click', () => {
      if (confirm('Start a new session? This will reset local session storage and initialize a fresh lab state.')) {
        this._resetSession();
      }
    });

    const prepareButton = document.getElementById('btn-prepare-trial');
    prepareButton.addEventListener('click', async () => {
      if (prepareButton.disabled) return;
      prepareButton.disabled = true;
      try {
        const snapshot = await this.api._request(`/api/sessions/${this.sessionId}/prepare`, {method:'POST',body:{}});
        this._updateSnapshot(snapshot);
        this._showToast('Mock apparatus prepared. Record a new prediction and choose the next sample.');
      } catch (err) { this._showToast(err.message,true); }
      finally { prepareButton.disabled = false; }
    });
    // Offline banner retry
    this.dom.btnRetryNetwork.addEventListener('click', () => {
      this._syncSnapshot();
    });

    // Proposals: Confirm
    this.dom.btnConfirmProposal.addEventListener('click', async () => {
      if (!this.snapshot?.pending?.request_id) return;
      try {
        const updated = await this.api.confirmProposal(this.sessionId, this.snapshot.pending.request_id);
        this._updateSnapshot(updated);
        this._showToast('Student confirmed. Waiting for backend and any required operator authorization.');
      } catch (err) {
        this._showToast(`Confirmation failed: ${err.message}`, true);
      }
    });

    // Proposals: Cancel
    this.dom.btnCancelProposal.addEventListener('click', async () => {
      const reqId = this.snapshot?.pending?.request_id;
      try {
        const updated = await this.api.cancelProposal(this.sessionId, reqId);
        this._updateSnapshot(updated);
        this._showToast('Proposal cancelled.');
      } catch (err) {
        this._showToast(`Cancellation failed: ${err.message}`, true);
      }
    });

    // Proposals: Parameter Correction (Invalidates old proposal per contract)
    this.dom.proposalCorrectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = this.dom.proposalCorrectInput.value.trim();
      if (!text) return;

      try {
        const clientReqId = this._generateRequestId('corr');
        const updated = await this.api.sendRequest(this.sessionId, text, clientReqId);
        this.dom.proposalCorrectInput.value = '';
        this._updateSnapshot(updated);
        this._showToast('Correction submitted. Previous proposal revised.');
      } catch (err) {
        this._showToast(`Correction error: ${err.message}`, true);
      }
    });

    // Text Command Pathway (Always available credential-free)
    this.dom.commandForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = this.dom.commandInput.value.trim();
      if (!text) return;

      try {
        const clientReqId = this._generateRequestId('cmd');
        const updated = await this.api.sendRequest(this.sessionId, text, clientReqId);
        if (this.dom.commandInput.value.trim() === text) this.dom.commandInput.value = '';
        this._updateSnapshot(updated);
      } catch (err) {
        this._showToast(`Command error: ${err.message}`, true);
      }
    });

    // Voice Mic Toggle (Header & Mobile)
    const toggleVoice = () => this._toggleVoiceCapture();
    this.dom.btnToggleMic.addEventListener('click', toggleVoice);
    this.dom.btnMobileMic.addEventListener('click', toggleVoice);

    // Voice Mute Toggle
    this.dom.btnToggleMute.addEventListener('click', () => {
      if (!this.liveClient) return;
      const willMute = !this.liveClient.isMuted;
      this.liveClient.setMuted(willMute);
    });

    // Disconnect Voice
    this.dom.btnDisconnectVoice.addEventListener('click', () => {
      if (this.liveClient) {
        this.liveClient.cleanup();
      }
    });

    // Prediction Form Submit
    this.dom.predictionForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = this.dom.predictionInput.value.trim();
      if (!text) return;

      try {
        const updated = await this.api.submitPrediction(this.sessionId, text);
        this._updateSnapshot(updated);
        this._showToast('Hypothesis recorded!');
      } catch (err) {
        this._showToast(`Failed to record prediction: ${err.message}`, true);
      }
    });

    // Prediction Edit Button
    this.dom.btnEditPrediction.addEventListener('click', () => {
      this.dom.predictionSavedContainer.style.display = 'none';
      this.dom.predictionForm.style.display = 'flex';
      this.dom.predictionInput.value = this.snapshot?.prediction || '';
      this.dom.predictionInput.focus();
    });

    // Quiz Form Submit
    this.dom.quizForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!this.snapshot?.quiz) return;

      let answer = null;
      if (this.snapshot.quiz.type === 'multiple_choice') {
        const selected = this.dom.quizForm.querySelector('input[name="quiz_choice"]:checked');
        if (!selected) {
          this._showToast('Please select an option before submitting.', true);
          return;
        }
        answer = selected.value;
      } else {
        answer = this.dom.quizFreeformInput.value.trim();
        if (!answer) {
          this._showToast('Please write your explanation before submitting.', true);
          return;
        }
      }

      try {
        const updated = await this.api.submitAnswer(this.sessionId, this.snapshot.quiz.id, answer);
        this._updateSnapshot(updated);
        this._showToast('Answer submitted!');
      } catch (err) {
        this._showToast(`Quiz submission failed: ${err.message}`, true);
      }
    });

    // Experiment Modal Open / Close
    this.dom.btnOpenExperiments.addEventListener('click', () => {
      this.dom.experimentModal.classList.add('active');
    });
    this.dom.btnCloseExperimentModal.addEventListener('click', () => {
      this.dom.experimentModal.classList.remove('active');
    });
    this.dom.experimentModal.addEventListener('click', (e) => {
      if (e.target === this.dom.experimentModal) {
        this.dom.experimentModal.classList.remove('active');
      }
    });

    // Export Notebook
    this.dom.btnExportNotebook.addEventListener('click', () => {
      this._exportNotebookReport();
    });

    // Developer Panel Actions
    this.dom.btnRefreshSkills.addEventListener('click', () => this._loadSkills());
    this.dom.btnComposeSkill.addEventListener('click', () => this._composeSkillCandidate());
    this.dom.btnTestCandidate.addEventListener('click', () => this._testComposedCandidate());
    this.dom.btnPromoteCandidate.addEventListener('click', () => this._promoteComposedCandidate());
  }

  // --- Session Management & Lifecycle ---

  async _loadHealth() {
    try {
      this.health = await this.api.getHealth();
      this._renderHealth();
    } catch (err) {
      console.warn('Health check unavailable:', err);
      // Fallback defaults
      this.health = {
        backend: 'mock',
        live_configured: false,
        live_model: 'unknown',
        expert_configured: false,
      };
      this._renderHealth();
    }
  }

  _renderHealth() {
    if (!this.health) return;

    // Backend pill
    const backend = (this.snapshot?.backend || this.health.backend || 'mock').toLowerCase();
    this.dom.badgeBackend.className = `pill pill-${backend}`;
    this.dom.badgeBackendText.textContent = `Backend: ${backend.toUpperCase()}`;

    // Live voice configured status
    if (this.health.live_configured === false) {
      this.dom.badgeVoice.className = 'pill pill-voice-unavailable';
      this.dom.badgeVoiceText.textContent = 'Voice: Unavailable';
      this.dom.liveFallbackBadge.style.display = 'inline-flex';
      this.dom.liveNoticeText.textContent = 'Gemini Live voice not configured on server. Deterministic local text pathway active.';
    }
  }

  async _loadExperiments() {
    try {
      const data = await this.api.getExperiments();
      this.experiments = Array.isArray(data) ? data : [];
      this._renderExperimentsModal();
    } catch (err) {
      console.warn('Could not load experiments:', err);
      this.experiments = [];
    }
  }

  async _initSession() {
    const savedId = localStorage.getItem('openarms_session_id');
    let snap = null;

    if (savedId) {
      try {
        snap = await this.api.getSession(savedId);
      } catch (err) {
        console.warn(`Could not restore session ${savedId}:`, err.message);
        snap = null;
      }
    }

    if (!snap) {
      snap = await this.api.createSession();
    }

    this.sessionId = snap.session_id;
    localStorage.setItem('openarms_session_id', this.sessionId);
    this.dom.sessionIdDisplay.textContent = this.sessionId;

    // Initialize Event WebSocket
    this._initEventsStream();

    // Update state
    this._updateSnapshot(snap);

    // If no experiment selected and experiments are available, prompt or set first
    if (!snap.experiment && this.experiments.length > 0) {
      try {
        const updated = await this.api.selectExperiment(this.sessionId, this.experiments[0].id);
        this._updateSnapshot(updated);
      } catch (e) {
        console.warn('Auto-select experiment failed:', e);
      }
    }
  }

  _initEventsStream() {
    if (this.eventsClient) {
      this.eventsClient.close();
    }

    this.eventsClient = new EventsClient(this.sessionId, {
      onState: (updatedSnapshot) => {
        this._updateSnapshot(updatedSnapshot);
      },
      onStatusChange: ({ connected, reconnecting, attempt }) => {
        if (connected) {
          this.dom.badgeConnection.className = 'pill pill-voice-active';
          this.dom.badgeConnectionText.textContent = 'Live Synced';
          this.dom.offlineBanner.classList.remove('active');
        } else if (reconnecting) {
          this.dom.badgeConnection.className = 'pill pill-voice-connecting';
          this.dom.badgeConnectionText.textContent = `Reconnecting (${attempt})...`;
          this.dom.offlineBannerText.textContent = `Connection lost. Reconnecting with exponential backoff (attempt ${attempt})...`;
          this.dom.offlineBanner.classList.add('active');
        } else {
          this.dom.badgeConnection.className = 'pill pill-voice-unavailable';
          this.dom.badgeConnectionText.textContent = 'Offline';
          this.dom.offlineBanner.classList.add('active');
        }
      },
      onResyncNeeded: () => {
        this._syncSnapshot();
      },
    });

    this.eventsClient.connect();
  }

  async _syncSnapshot() {
    if (!this.sessionId) return;
    try {
      const snap = await this.api.getSession(this.sessionId);
      this._updateSnapshot(snap);
      this.dom.offlineBanner.classList.remove('active');
    } catch (err) {
      console.warn('Snapshot resync failed:', err);
    }
  }

  async _resetSession() {
    if (this.eventsClient) {
      this.eventsClient.close();
      this.eventsClient = null;
    }
    if (this.liveClient) {
      this.liveClient.cleanup();
      this.liveClient = null;
    }

    localStorage.removeItem('openarms_session_id');

    try {
      const freshSnap = await this.api.createSession();
      this.sessionId = freshSnap.session_id;
      localStorage.setItem('openarms_session_id', this.sessionId);
      this.dom.sessionIdDisplay.textContent = this.sessionId;

      this._initEventsStream();
      this._updateSnapshot(freshSnap);
      this._showToast('New lab session initialized.');
    } catch (err) {
      this._showToast(`Session reset failed: ${err.message}`, true);
    }
  }

  async _triggerEmergencyStop() {
    if (!this.sessionId) return;
    try {
      // Audible beep for confirmation if audio context exists
      this._playStopAlertSound();

      const updated = await this.api.emergencyStop(this.sessionId);
      this._updateSnapshot(updated);
      this._showToast('STOP requested. Check execution status; controller stop behavior applies.', true);
    } catch (err) {
      this._showToast(`Emergency STOP request error: ${err.message}`, true);
    }
  }

  _playStopAlertSound() {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.setValueAtTime(220, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    } catch (e) {
      // ignore
    }
  }

  // --- Voice & AudioWorklet Stream ---

  async _toggleVoiceCapture() {
    if (!this.sessionId) return;

    if (!this.liveClient) {
      this.liveClient = new LiveClient(this.sessionId, {
        onStatusChange: ({ status, message, isLiveAvailable, isMuted }) => {
          this._handleLiveStatus(status, message, isLiveAvailable, isMuted);
        },
        onTranscript: ({ role, text }) => {
          this._appendTranscript(role, text);
        },
        onInterrupted: () => {
          this._showToast('Assistant speech interrupted by student voice');
        },
        onError: ({ message }) => {
          this._showToast(`Voice error: ${message}`, true);
        },
        onAudioLevel: (rms) => {
          const pct = Math.min(100, Math.round(rms * 400));
          this.dom.audioLevelFill.style.width = `${pct}%`;
        },
      });
    }

    if (['active', 'connecting', 'reconnecting', 'muted'].includes(this.liveClient.status)) {
      this.liveClient.cleanup();
    } else {
      try {
        await this.liveClient.startVoice();
      } catch (err) {
        console.warn('Voice start failed:', err);
      }
    }
  }

  _handleLiveStatus(status, message, isLiveAvailable, isMuted) {
    const connected = ['active', 'connecting', 'muted', 'reconnecting'].includes(status);
    for (const button of [this.dom.btnToggleMic, this.dom.btnMobileMic]) {
      button.setAttribute('aria-pressed', String(connected));
      button.setAttribute('aria-label', connected ? 'Disconnect voice microphone' : 'Start voice microphone');
    }
    if (status === 'active' || status === 'muted') {
      this.dom.liveFallbackBadge.style.display = 'none';
      this.dom.liveNoticeText.textContent = 'Gemini Live connected. Review and confirm every proposed action below.';
    }
    // Update Voice Badge in Header
    if (status === 'active') {
      this.dom.badgeVoice.className = 'pill pill-voice-active';
      this.dom.badgeVoiceText.textContent = 'Voice: Active';
      this.dom.btnToggleMic.className = 'btn-mic active';
      this.dom.micIcon.textContent = '🎙️';
      this.dom.micPulseRing.classList.add('active');
      this.dom.voiceStatusText.textContent = 'Listening (Speak naturally)';
      this.dom.btnToggleMute.disabled = false;
      this.dom.btnDisconnectVoice.disabled = false;
    } else if (status === 'muted') {
      this.dom.badgeVoice.className = 'pill pill-voice-connecting';
      this.dom.badgeVoiceText.textContent = 'Voice: Muted';
      this.dom.btnToggleMic.className = 'btn-mic muted';
      this.dom.micIcon.textContent = '🔇';
      this.dom.micPulseRing.classList.remove('active');
      this.dom.voiceStatusText.textContent = 'Microphone Muted';
      this.dom.btnToggleMute.disabled = false;
      this.dom.muteText.textContent = 'Unmute';
      this.dom.muteIcon.textContent = '🎙️';
    } else if (status === 'connecting' || status === 'reconnecting') {
      this.dom.badgeVoice.className = 'pill pill-voice-connecting';
      this.dom.badgeVoiceText.textContent = 'Voice: Connecting...';
      this.dom.voiceStatusText.textContent = 'Connecting Voice...';
      this.dom.micPulseRing.classList.remove('active');
    } else if (status === 'unavailable') {
      this.dom.badgeVoice.className = 'pill pill-voice-unavailable';
      this.dom.badgeVoiceText.textContent = 'Voice: Unavailable';
      this.dom.btnToggleMic.className = 'btn-mic';
      this.dom.micIcon.textContent = '🎤';
      this.dom.micPulseRing.classList.remove('active');
      this.dom.voiceStatusText.textContent = 'Live Voice Unavailable';
      this.dom.liveFallbackBadge.style.display = 'inline-flex';
      this.dom.liveNoticeText.textContent = message || 'Live voice service unavailable. Using deterministic local text pathway.';
      this.dom.btnToggleMute.disabled = true;
      this.dom.btnDisconnectVoice.disabled = true;
    } else {
      // Disconnected or Error
      this.dom.badgeVoice.className = 'pill pill-voice-unavailable';
      this.dom.badgeVoiceText.textContent = 'Voice: Inactive';
      this.dom.btnToggleMic.className = 'btn-mic';
      this.dom.micIcon.textContent = '🎤';
      this.dom.micPulseRing.classList.remove('active');
      this.dom.voiceStatusText.textContent = 'Click mic to start voice';
      this.dom.audioLevelFill.style.width = '0%';
      this.dom.btnToggleMute.disabled = true;
      this.dom.btnDisconnectVoice.disabled = true;
      this.dom.muteText.textContent = 'Mute';
      this.dom.muteIcon.textContent = '🔇';
    }
  }

  _appendTranscript(role, text) {
    const entry = document.createElement('div');
    entry.className = 'transcript-entry';

    const roleTag = document.createElement('span');
    roleTag.className = `transcript-role ${role === 'user' ? 'user' : 'assistant'}`;
    roleTag.textContent = role === 'user' ? 'Student' : 'Assistant';

    const textSpan = document.createElement('span');
    textSpan.className = 'transcript-text';
    textSpan.textContent = text;

    entry.appendChild(roleTag);
    entry.appendChild(textSpan);

    this.dom.transcriptFeed.appendChild(entry);
    this.dom.transcriptFeed.scrollTop = this.dom.transcriptFeed.scrollHeight;
  }

  // --- Snapshot Rendering & UI State Synchronization ---

  _updateSnapshot(snap) {
    if (!snap) return;
    // In-flight responses and events from a retired session cannot restore it.
    if (this.sessionId && snap.session_id !== this.sessionId) return;
    const sessionChanged = this.snapshot?.session_id !== snap.session_id;
    this.snapshot = snap;
    document.getElementById('btn-prepare-trial').hidden = snap.backend !== 'mock';

    // 1. Session ID display
    if (snap.session_id) {
      this.sessionId = snap.session_id;
      this.dom.sessionIdDisplay.textContent = snap.session_id;
    }

    // 2. Health & Backend Pill
    this._renderHealth();

    // 3. Render Proposal Section (Pending confirmation)
    this._renderProposal(snap.pending);

    // 4. Render Current Experiment
    this._renderExperiment(snap.experiment);

    // 5. Render Prediction
    this._renderPrediction(snap.prediction, sessionChanged);

    // 6. Render Arm State & Bench Pods
    this._renderBenchState(snap.state);

    // 7. Render Observations with Provenance
    this._renderObservations(snap.observations);

    // 8. Render Quiz Checkpoint
    this._renderQuiz(snap.quiz);

    // 9. Render Notebook Events Timeline
    this._renderNotebook(snap.notebook);

    // 10. Render Message Log
    this._renderMessages(snap.messages);

    // 11. Render Dev Snapshot
    this.dom.snapshotInspector.textContent = JSON.stringify(snap, null, 2);
  }

  _renderProposal(pending) {
    if (this.proposalCountdownInterval) {
      clearInterval(this.proposalCountdownInterval);
      this.proposalCountdownInterval = null;
    }
    if (!pending) {
      this.dom.proposalSection.style.display = 'none';
      if (this.proposalCountdownInterval) {
        clearInterval(this.proposalCountdownInterval);
        this.proposalCountdownInterval = null;
      }
      return;
    }

    this.dom.proposalSection.style.display = 'flex';
    this.dom.proposalSummary.textContent = pending.summary || `Execute skill ${pending.skill_id}`;
    this.dom.proposalSkillId.textContent = pending.skill_id || 'unknown';
    this.dom.proposalParameters.textContent = JSON.stringify(pending.parameters || {}, null, 2);
    this.dom.proposalRequestId.textContent = pending.request_id || 'none';
    this.dom.btnConfirmProposal.disabled = false;

    // Handle expiration countdown if present
    if (pending.expires_at) {
      this.dom.proposalExpiresRow.style.display = 'table-row';
      const updateTimer = () => {
        const remainingMs = epochDate(pending.expires_at).getTime() - Date.now();
        if (remainingMs <= 0) {
          this.dom.proposalExpiresVal.textContent = 'Expired';
          this.dom.btnConfirmProposal.disabled = true;
          if (this.proposalCountdownInterval) {
            clearInterval(this.proposalCountdownInterval);
            this.proposalCountdownInterval = null;
          }
        } else {
          this.dom.proposalExpiresVal.textContent = `${Math.ceil(remainingMs / 1000)}s`;
        }
      };
      updateTimer();
      if (this.proposalCountdownInterval) clearInterval(this.proposalCountdownInterval);
      this.proposalCountdownInterval = setInterval(updateTimer, 1000);
    } else {
      this.dom.proposalExpiresRow.style.display = 'none';
    }
  }

  _renderExperiment(exp) {
    if (!exp) {
      this.dom.experimentTitle.textContent = 'No Experiment Selected';
      this.dom.experimentQuestion.textContent = 'Choose an experiment to begin testing hypotheses.';
      this.dom.experimentInstructions.textContent = '';
      this.dom.experimentIndepVar.textContent = 'Independent: none';
      this.dom.experimentControlledVars.innerHTML = '';
      return;
    }

    this.dom.experimentTitle.textContent = exp.title || exp.id || 'Current Experiment';
    this.dom.experimentQuestion.textContent = exp.question || '';
    this.dom.experimentInstructions.textContent = exp.instructions || '';
    this.dom.experimentIndepVar.textContent = `Independent: ${exp.independent_variable || 'None'}`;

    this.dom.experimentControlledVars.innerHTML = '';
    const controlled = exp.controlled_variables || [];
    controlled.forEach((ctrl) => {
      const tag = document.createElement('span');
      tag.className = 'var-tag';
      tag.textContent = `Control: ${ctrl}`;
      this.dom.experimentControlledVars.appendChild(tag);
    });
  }

  _renderExperimentsModal() {
    this.dom.experimentsListContainer.innerHTML = '';
    if (this.experiments.length === 0) {
      this.dom.experimentsListContainer.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">No experiments available.</p>';
      return;
    }

    this.experiments.forEach((exp) => {
      const card = document.createElement('div');
      card.className = 'experiment-meta-box';
      card.style.cursor = 'pointer';

      card.innerHTML = `
        <h3 style="font-size: 1rem; font-weight: 700; color: #fff;">${escapeHtml(exp.title || exp.id)}</h3>
        <p style="font-size: 0.9rem; color: #38bdf8; font-weight: 600;">${escapeHtml(exp.question || '')}</p>
        <p style="font-size: 0.8rem; color: var(--text-secondary);">${escapeHtml(exp.instructions || '')}</p>
        <div style="margin-top: 6px;">
          <button type="button" class="btn-primary" style="font-size: 0.82rem; min-height: 36px; padding: 6px 12px;">Select This Experiment</button>
        </div>
      `;

      card.querySelector('button').addEventListener('click', async () => {
        try {
          const updated = await this.api.selectExperiment(this.sessionId, exp.id);
          this._updateSnapshot(updated);
          this.dom.experimentModal.classList.remove('active');
          this._showToast(`Switched experiment to: ${escapeHtml(exp.title || exp.id)}`);
        } catch (err) {
          this._showToast(`Failed to switch experiment: ${err.message}`, true);
        }
      });

      this.dom.experimentsListContainer.appendChild(card);
    });
  }

  _renderPrediction(prediction, sessionChanged = false) {
    // Keep unsaved writing and the edit form intact across streamed state updates.
    if (!sessionChanged && this.renderedPrediction === prediction) return;
    this.renderedPrediction = prediction;
    if (prediction && prediction.trim()) {
      this.dom.predictionSavedContainer.style.display = 'flex';
      this.dom.predictionSavedDisplay.textContent = `"${prediction.trim()}"`;
      this.dom.predictionForm.style.display = 'none';
    } else {
      this.dom.predictionSavedContainer.style.display = 'none';
      this.dom.predictionForm.style.display = 'flex';
      this.dom.predictionInput.value = '';
    }
  }

  _renderBenchState(state) {
    const s = state || {};

    // Stage
    const stage = s.stage || this.snapshot?.requests?.at(-1)?.status || 'ready';
    this.dom.armStageTag.textContent = `Stage: ${stage}`;

    // Arm state metrics
    this.dom.armStatusVal.textContent = this.snapshot?.requests?.at(-1)?.status || 'idle';
    const unverified = this.snapshot?.backend === 'physical' || this.snapshot?.state_provenance === 'UNKNOWN';
    this.dom.armGripperVal.textContent = unverified ? 'unknown' : (s.gripper || (s.holding ? 'closed (holding)' : 'open'));
    this.dom.armPositionVal.textContent = unverified ? 'unknown' : (s.at || s.arm_pose || s.position || 'unknown');
    this.dom.armSafetyVal.textContent = s.armed === true ? 'armed' : s.armed === false ? 'disarmed' : 'unknown';

    // Station pods
    const staContents = unverified ? 'unknown' : (s.point_holds?.A || 'empty');
    const stbContents = unverified ? 'unknown' : (s.point_holds?.B || 'empty');

    this.dom.stationAContents.textContent = staContents;
    this.dom.stationBContents.textContent = stbContents;
    document.getElementById('station-c-contents').textContent = unverified ? 'unknown' : (s.point_holds?.C || 'empty');
    for (const station of ['a', 'b', 'c']) {
      const point = station.toUpperCase();
      document.getElementById(`station-${station}-pod`).classList.toggle('active', !unverified && (s.at === point || s.target === point));
      document.getElementById(`station-${station}-status`).textContent = unverified ? 'Unverified setup' : (s.point_holds?.[point] ? 'Occupied' : 'Empty');
    }
  }

  _renderObservations(observations) {
    const list = Array.isArray(observations) ? observations : [];
    this.dom.observationsCount.textContent = `${list.length} observation${list.length === 1 ? '' : 's'}`;

    if (list.length === 0) {
      this.dom.noObservationsMsg.style.display = 'block';
      this.dom.observationsList.innerHTML = '';
      this.dom.observationsList.appendChild(this.dom.noObservationsMsg);
      return;
    }

    this.dom.noObservationsMsg.style.display = 'none';
    this.dom.observationsList.innerHTML = '';

    list.forEach((obs) => {
      const item = document.createElement('article');
      item.className = 'observation-item';

      const prov = (obs.provenance || 'UNKNOWN').toUpperCase();
      let provClass = 'provenance-unknown';
      let provLabel = 'UNKNOWN PROVENANCE';

      if (prov.startsWith('MOCK')) {
        provClass = 'provenance-model-predicted';
        provLabel = 'MOCK';
      } else if (prov.includes('PHYSICAL') || prov.includes('BENCH') || prov.includes('REAL')) {
        provClass = 'provenance-physical';
        provLabel = 'PHYSICAL BENCH';
      } else if (prov.includes('SIMULAT') || prov.includes('ISAAC')) {
        provClass = 'provenance-simulated';
        provLabel = 'SIMULATED';
      } else if (prov.includes('MODEL') || prov.includes('PREDICT')) {
        provClass = 'provenance-model-predicted';
        provLabel = 'MODEL-PREDICTED';
      }

      const timeFormatted = obs.timestamp ? epochDate(obs.timestamp).toLocaleTimeString() : '';

      item.innerHTML = `
        <div class="observation-header">
          <span class="provenance-tag ${provClass}">${provLabel}</span>
          <span class="observation-time">${timeFormatted}</span>
        </div>
        <p class="observation-text">${escapeHtml(obs.text || JSON.stringify(obs))}</p>
      `;

      this.dom.observationsList.appendChild(item);
    });

    this.dom.observationsList.scrollTop = this.dom.observationsList.scrollHeight;
  }

  _renderQuiz(quiz) {
    if (!quiz) {
      this.dom.quizSection.style.display = 'none';
      this.renderedQuizId = null;
      return;
    }

    this.dom.quizSection.style.display = 'flex';
    this.dom.quizPrompt.textContent = quiz.prompt || 'Reflection Question';

    if (this.renderedQuizId === quiz.id) return;
    this.renderedQuizId = quiz.id;
    this.dom.quizFreeformInput.value = '';
    this.dom.quizOptionsContainer.innerHTML = '';
    if (quiz.type === 'multiple_choice' && Array.isArray(quiz.options)) {
      this.dom.quizOptionsContainer.style.display = 'flex';
      this.dom.quizFreeformContainer.style.display = 'none';

      quiz.options.forEach((opt, idx) => {
        const label = document.createElement('label');
        label.className = 'quiz-option-label';
        label.innerHTML = `
          <input type="radio" name="quiz_choice" value="${escapeHtml(opt)}" id="quiz_opt_${idx}" required>
          <span style="font-size: 0.9rem; color: #fff;">${escapeHtml(opt)}</span>
        `;
        this.dom.quizOptionsContainer.appendChild(label);
      });
    } else {
      this.dom.quizOptionsContainer.style.display = 'none';
      this.dom.quizFreeformContainer.style.display = 'block';
    }
  }

  _renderNotebook(events) {
    const list = Array.isArray(events) ? events : [];
    if (list.length === 0) {
      this.dom.noNotebookMsg.style.display = 'block';
      this.dom.notebookTimeline.innerHTML = '';
      this.dom.notebookTimeline.appendChild(this.dom.noNotebookMsg);
      return;
    }

    this.dom.noNotebookMsg.style.display = 'none';
    this.dom.notebookTimeline.innerHTML = '';

    list.forEach((evt) => {
      const entry = document.createElement('div');
      entry.className = 'notebook-entry';

      const timeStr = evt.time ? epochDate(evt.time).toLocaleTimeString() : '';
      const kind = evt.kind || 'event';
      const dataStr = typeof evt.data === 'string' ? evt.data : JSON.stringify(evt.data || {});

      entry.innerHTML = `
        <div style="display:flex; justify-content:space-between;">
          <strong style="color:var(--accent-cyan); text-transform:uppercase; font-size:0.75rem;">${escapeHtml(kind)}</strong>
          <span class="notebook-entry-time">${timeStr}</span>
        </div>
        <div style="color:var(--text-secondary); word-break:break-word;">${escapeHtml(dataStr)}</div>
      `;

      this.dom.notebookTimeline.appendChild(entry);
    });

    this.dom.notebookTimeline.scrollTop = this.dom.notebookTimeline.scrollHeight;
  }

  _renderMessages(messages) {
    const list = Array.isArray(messages) ? messages : [];
    if (list.length === 0) {
      this.dom.noMessagesMsg.style.display = 'block';
      this.dom.messagesTimeline.innerHTML = '';
      this.dom.messagesTimeline.appendChild(this.dom.noMessagesMsg);
      return;
    }

    this.dom.noMessagesMsg.style.display = 'none';
    this.dom.messagesTimeline.innerHTML = '';

    list.forEach((msg) => {
      const entry = document.createElement('div');
      entry.className = 'notebook-entry';
      entry.style.borderLeftColor = msg.role === 'user' ? 'var(--accent-blue)' : 'var(--accent-green)';

      entry.innerHTML = `
        <strong style="font-size:0.72rem; color:${msg.role === 'user' ? '#93c5fd' : '#86efac'}; text-transform:uppercase;">
          ${escapeHtml(msg.role || 'message')}
        </strong>
        <div style="color:#f8fafc; font-size:0.85rem; margin-top:2px;">${escapeHtml(msg.text || '')}</div>
      `;

      this.dom.messagesTimeline.appendChild(entry);
    });

    this.dom.messagesTimeline.scrollTop = this.dom.messagesTimeline.scrollHeight;
  }

  _exportNotebookReport() {
    if (!this.snapshot) return;

    const snap = this.snapshot;
    const now = new Date().toISOString();
    let md = `# OpenArms Lab Scientific Report\n\n`;
    md += `- **Date/Time:** ${now}\n`;
    md += `- **Session ID:** \`${snap.session_id}\`\n`;
    md += `- **Execution Backend:** \`${snap.backend || 'mock'}\`\n`;
    md += `- **Experiment:** ${snap.experiment?.title || 'None'}\n\n`;

    md += `## 1. Scientific Inquiry\n`;
    md += `- **Question:** ${snap.experiment?.question || 'N/A'}\n`;
    md += `- **Independent Variable:** ${snap.experiment?.independent_variable || 'N/A'}\n`;
    md += `- **Controlled Variables:** ${(snap.experiment?.controlled_variables || []).join(', ') || 'N/A'}\n\n`;

    md += `## 2. Student Hypothesis & Prediction\n`;
    md += `> ${snap.prediction || 'No prediction recorded'}\n\n`;

    md += `## 3. Observed Outcomes & Evidence (Truthful Provenance)\n`;
    if (snap.observations && snap.observations.length > 0) {
      snap.observations.forEach((obs, idx) => {
        md += `${idx + 1}. **[${(obs.provenance || 'UNKNOWN').toUpperCase()}]** ${obs.text}\n`;
      });
    } else {
      md += `*No observations recorded.*\n`;
    }
    md += `\n*Integrity Note: Simulated/Model outcomes are explicitly marked and distinct from physical measurements.*\n\n`;

    md += `## 4. Lab Notebook Timeline\n`;
    if (snap.notebook && snap.notebook.length > 0) {
      snap.notebook.forEach((evt) => {
        md += `- **${evt.time || ''} [${evt.kind}]**: ${JSON.stringify(evt.data)}\n`;
      });
    }

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `openarms-lab-report-${snap.session_id}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    this._showToast('Lab report exported to Markdown.');
  }

  // --- Skills Registry & Expert Composer ---

  async _loadSkills() {
    try {
      const data = await this.api.getSkills();
      this.skills = Array.isArray(data) ? data : (data?.skills || []);
      this._renderSkillsTable();
    } catch (err) {
      console.warn('Could not load skills registry:', err);
      // Fallback to skills in snapshot
      if (this.snapshot?.skills) {
        this.skills = this.snapshot.skills;
        this._renderSkillsTable();
      }
    }
  }

  _renderSkillsTable() {
    this.dom.skillsTableBody.innerHTML = '';
    if (this.skills.length === 0) {
      this.dom.skillsTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:12px;">No skills registered.</td></tr>';
      return;
    }

    this.skills.forEach((skill) => {
      skill = {...skill, id: skill.skill_id || skill.id};
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:var(--font-mono);font-weight:600;color:var(--accent-cyan);">${escapeHtml(skill.id)}</td>
        <td>${escapeHtml(skill.name || skill.id)}</td>
        <td style="color:var(--text-secondary);">${escapeHtml(skill.description || 'No description')}</td>
        <td>
          <button type="button" class="btn-icon btn-test-skill" data-id="${escapeHtml(skill.id)}" style="padding:2px 8px;font-size:0.75rem;min-height:28px;">Test</button>
        </td>
      `;

      tr.querySelector('.btn-test-skill').addEventListener('click', async () => {
        try {
          const res = await this.api.testSkill(skill.id);
          this._showToast(`Skill test executed: ${JSON.stringify(res)}`);
        } catch (e) {
          this._showToast(`Skill test failed: ${e.message}`, true);
        }
      });

      this.dom.skillsTableBody.appendChild(tr);
    });
  }

  async _composeSkillCandidate() {
    if (this.dom.btnComposeSkill.disabled) return;
    const instruction = this.dom.skillComposeInput.value.trim();
    if (!instruction) {
      this._showToast('Please type an instruction to compose.', true);
      return;
    }

    try {
      this.dom.btnComposeSkill.disabled = true;
      this.composedCandidate = null;
      this.candidateEvidenceId = null;
      this.dom.composedCandidatePreview.style.display = 'none';
      this._showToast('Expert agent compiling skill candidate...');
      const candidate = await this.api.composeSkill(instruction);
      this.composedCandidate = {...candidate, id: candidate.skill_id || candidate.id};
      this.candidateEvidenceId = null;
      this.dom.btnPromoteCandidate.disabled = true;
      this.dom.candidateJsonPreview.textContent = JSON.stringify(candidate, null, 2);
      this.dom.composedCandidatePreview.style.display = 'flex';
      this._showToast('Skill candidate compiled!');
    } catch (err) {
      this._showToast(`Composition failed: ${err.message}`, true);
    } finally { this.dom.btnComposeSkill.disabled = false; }
  }

  async _testComposedCandidate() {
    if (!this.composedCandidate?.id) {
      this._showToast('No active candidate to test.', true);
      return;
    }

    const candidateId = this.composedCandidate.id;
    this.candidateEvidenceId = null;
    this.dom.btnPromoteCandidate.disabled = true;
    try {
      const res = await this.api.testSkill(candidateId);
      if (this.composedCandidate?.id !== candidateId) return;
      this.candidateEvidenceId = res.evidence_id;
      this.dom.btnPromoteCandidate.disabled = !res.evidence_id || res.verdict !== 'passed';
      this._showToast(`Candidate test completed: ${JSON.stringify(res)}`);
    } catch (err) {
      this._showToast(`Candidate test error: ${err.message}`, true);
    }
  }

  async _promoteComposedCandidate() {
    if (!this.composedCandidate?.id) {
      this._showToast('No active candidate to promote.', true);
      return;
    }

    try {
      const evidenceId = this.candidateEvidenceId;
      if (!evidenceId) throw new Error("Test this candidate before promotion.");
      const res = await this.api.promoteSkill(this.composedCandidate.id, evidenceId);
      this._showToast(`Candidate promoted to active skills: ${this.composedCandidate.id}`);
      this._loadSkills();
    } catch (err) {
      this._showToast(`Promotion failed: ${err.message}`, true);
    }
  }

  // --- Utilities ---

  _generateRequestId(prefix = 'req') {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
  }

  _showToast(msg, isError = false) {
    const toast = document.createElement('div');
    toast.className = 'pill';
    toast.style.position = 'fixed';
    toast.style.bottom = '24px';
    toast.style.right = '24px';
    toast.style.zIndex = '9999';
    toast.style.background = isError ? '#7f1d1d' : '#064e3b';
    toast.style.color = isError ? '#fecaca' : '#a7f3d0';
    toast.style.border = `1px solid ${isError ? '#ef4444' : '#10b981'}`;
    toast.style.boxShadow = '0 10px 15px -3px rgba(0,0,0,0.5)';
    toast.style.padding = '8px 16px';
    toast.style.fontSize = '0.85rem';
    toast.setAttribute('role', isError ? 'alert' : 'status');
    toast.classList.add('app-toast');
    toast.textContent = msg;

    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.transition = 'opacity 0.3s ease';
      toast.style.opacity = '0';
      setTimeout(() => document.body.removeChild(toast), 300);
    }, 3500);
  }
}

// Instantiate and boot application on DOM load
window.addEventListener('DOMContentLoaded', () => {
  const app = new OpenArmsApp();
  app.init();
  window.openArmsApp = app;
});
