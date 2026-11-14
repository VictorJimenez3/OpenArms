/**
 * OpenArms Lab - Events WebSocket Client
 *
 * Connects to WS /api/sessions/{id}/events.
 * Receives { type: 'state', state: snapshot }.
 * Automatically reconnects with exponential backoff.
 * On reconnect, triggers a snapshot resync callback.
 */

export class EventsClient {
  constructor(sessionId, options = {}) {
    this.sessionId = sessionId;
    this.baseUrl = options.baseUrl || '';
    this.onState = options.onState || (() => {});
    this.onStatusChange = options.onStatusChange || (() => {});
    this.onResyncNeeded = options.onResyncNeeded || (() => {});

    this.ws = null;
    this.isClosedManually = false;
    this.reconnectAttempt = 0;
    this.reconnectTimer = null;
    this.maxReconnectDelay = 10000;
    this.baseDelay = 1000;
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
        // fallback to default
      }
    }

    return `${protocol}//${host}/api/sessions/${encodeURIComponent(this.sessionId)}/events`;
  }

  connect() {
    this.isClosedManually = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const wsUrl = this._buildWsUrl();
    this.onStatusChange({ connected: false, connecting: true, attempt: this.reconnectAttempt });

    try {
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      this._handleDisconnect(err);
      return;
    }

    this.ws.onopen = () => {
      const wasReconnecting = this.reconnectAttempt > 0;
      this.reconnectAttempt = 0;
      this.onStatusChange({ connected: true, connecting: false });

      if (wasReconnecting) {
        // Fetch snapshot to ensure no events were missed during disconnection
        this.onResyncNeeded();
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'state' && payload.state) {
          this.onState(payload.state);
        }
      } catch (parseError) {
        console.warn('[EventsClient] Failed to parse event JSON:', parseError);
      }
    };

    this.ws.onerror = (err) => {
      // onerror is always followed by onclose
    };

    this.ws.onclose = () => {
      if (!this.isClosedManually) {
        this._handleDisconnect();
      }
    };
  }

  _handleDisconnect() {
    this.onStatusChange({ connected: false, connecting: false, reconnecting: true, attempt: this.reconnectAttempt + 1 });

    const delay = Math.min(
      this.maxReconnectDelay,
      this.baseDelay * Math.pow(1.5, this.reconnectAttempt) + Math.random() * 500
    );
    this.reconnectAttempt++;

    this.reconnectTimer = setTimeout(() => {
      if (!this.isClosedManually) {
        this.connect();
      }
    }, delay);
  }

  close() {
    this.isClosedManually = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {
        // ignore
      }
      this.ws = null;
    }
    this.onStatusChange({ connected: false, connecting: false, reconnecting: false });
  }
}
