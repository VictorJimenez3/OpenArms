/**
 * OpenArms Lab - REST API Client
 *
 * Implements the full OpenArms Lab API contract.
 * All session mutations return an updated snapshot.
 * Errors return { detail: string | object }.
 * Works credential-free.
 */

export class ApiError extends Error {
  constructor(message, status, detail = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export class LabApiClient {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  async _request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Accept': 'application/json',
      ...(options.headers || {}),
    };

    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    let response;
    try {
      response = await fetch(url, { ...options, headers });
    } catch (networkError) {
      throw new ApiError(
        `Network error connecting to ${endpoint}: ${networkError.message}`,
        0,
        { networkError: networkError.message }
      );
    }

    let data = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch (parseError) {
        data = null;
      }
    } else {
      const text = await response.text();
      data = text ? { raw: text } : null;
    }

    if (!response.ok) {
      const detail = data && data.detail ? data.detail : (data || response.statusText);
      const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
      throw new ApiError(message || `HTTP ${response.status}`, response.status, detail);
    }

    return data;
  }

  // System & Meta endpoints
  async getHealth() {
    return this._request('/api/health');
  }

  async getExperiments() {
    return this._request('/api/experiments');
  }

  // Session lifecycle
  async createSession() {
    return this._request('/api/sessions', {
      method: 'POST',
      body: {},
    });
  }

  async getSession(sessionId) {
    if (!sessionId) throw new Error('sessionId is required');
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}`);
  }

  async selectExperiment(sessionId, experimentId) {
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/experiment`, {
      method: 'POST',
      body: { experiment_id: experimentId },
    });
  }

  async submitPrediction(sessionId, text) {
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/prediction`, {
      method: 'POST',
      body: { text },
    });
  }

  async sendRequest(sessionId, text, clientRequestId = null) {
    const payload = { text };
    if (clientRequestId) {
      payload.client_request_id = clientRequestId;
    }
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/request`, {
      method: 'POST',
      body: payload,
    });
  }

  async confirmProposal(sessionId, requestId) {
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/confirm`, {
      method: 'POST',
      body: { request_id: requestId },
    });
  }

  async cancelProposal(sessionId, requestId = null) {
    const payload = requestId ? { request_id: requestId } : {};
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/cancel`, {
      method: 'POST',
      body: payload,
    });
  }

  async emergencyStop(sessionId) {
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/stop`, {
      method: 'POST',
      body: {},
    });
  }

  async submitAnswer(sessionId, questionId, answer) {
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/answer`, {
      method: 'POST',
      body: {
        question_id: questionId,
        answer,
      },
    });
  }

  async disconnectSession(sessionId) {
    return this._request(`/api/sessions/${encodeURIComponent(sessionId)}/disconnect`, {
      method: 'POST',
      body: {},
    });
  }

  // Skills Registry & Diagnostics endpoints
  async getSkills() {
    return this._request('/api/skills');
  }

  async composeSkill(instruction) {
    return this._request('/api/skills/compose', {
      method: 'POST',
      body: { instruction },
    });
  }

  async testSkill(skillId) {
    return this._request(`/api/skills/${encodeURIComponent(skillId)}/test`, {
      method: 'POST',
      body: {},
    });
  }

  async promoteSkill(skillId, evidenceId) {
    return this._request(`/api/skills/${encodeURIComponent(skillId)}/promote`, {
      method: 'POST',
      body: { evidence_id: evidenceId },
    });
  }
}
