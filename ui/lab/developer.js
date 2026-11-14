// Developer diagnostics read the same authenticated snapshot and voice state as the lab.
const $ = selector => document.querySelector(selector);
const humanize = value => typeof value === 'string' ? value.replaceAll('_', ' ') : '';
const duration = value => Number.isFinite(value) ? `${Math.round(value)} ms` : '';
const words = values => values.filter(value => typeof value === 'string' && value).join(' · ');
const count = (n, label) => Number.isFinite(n) ? `${n} ${label}` : '';
const list = (values, render) => Array.isArray(values) ? values.map(render).filter(Boolean) : [];

function element(tag, content) {
  const node = document.createElement(tag);
  if (content) node.textContent = content;
  return node;
}

function setText(target, content) {
  if (target.textContent !== content) target.textContent = content;
}

function rows(target, fields) {
  target.replaceChildren(...fields.flatMap(([name, value]) =>
    ['string', 'number', 'boolean'].includes(typeof value) && value !== ''
      ? [element('dt', name), element('dd', String(value))]
      : []));
}

function receipt(label, fields) {
  const item = element('li');
  const details = element('details');
  const content = element('dl');
  content.className = 'status-grid';
  rows(content, fields);
  details.append(element('summary', label), content);
  item.append(details);
  return item;
}

const traceKinds = new Map(Object.entries({
  expert_started: 'Expert started', expert_finished: 'Expert finished',
  expert_call_started: 'Model call started', expert_call_completed: 'Model call completed',
  expert_tool_started: 'Tool started', expert_tool_completed: 'Tool completed',
  expert_result: 'Expert decision', perception_result: 'Perception result',
  scene_unavailable: 'Scene unavailable', request_proposed: 'Proposal prepared',
  execution_progress: 'Execution progress', execution_checkpoint: 'Execution checkpoint',
  execution_result: 'Execution result', observation: 'Independent observation',
  skill_registered: 'Skill registered', skill_activated: 'Skill activated',
  skill_evaluation_started: 'Skill evaluation started', skill_evaluation: 'Skill evaluation',
  skill_evaluation_failed: 'Skill evaluation failed', stop_requested: 'Stop requested',
}));

export class DeveloperView {
  #api;
  #views = new Map();
  #traceCache;
  #skillCache;
  #statusCache;
  #warningCache;

  constructor(api) { this.#api = api; }

  release() {
    this.#releaseMedia('frame', 'No simulation frame yet.');
    this.#releaseMedia('video', 'No execution recording yet.');
    setText($('#simulation-status'), 'Waiting for session');
    this.#showSimulationMetrics();
  }

  #releaseMedia(slot, message) {
    const current = this.#views.get(slot);
    this.#views.delete(slot);
    current?.controller.abort();
    if (current?.media instanceof HTMLVideoElement) current.media.pause();
    current?.media?.removeAttribute('src');
    if (current?.media instanceof HTMLVideoElement) current.media.load();
    if (current?.url) URL.revokeObjectURL(current.url);
    $('#simulation-' + slot).replaceChildren();
    const status = $('#simulation-' + slot + '-state');
    setText(status, message);
    status.hidden = false;
  }

  async #loadMedia(slot, source, snapshot) {
    const video = slot === 'video';
    const label = video ? 'execution recording' : 'simulation frame';
    const key = JSON.stringify([snapshot?.session_id, snapshot?.generation, source]);
    if (this.#views.get(slot)?.key === key) return;
    if (!source) {
      this.#releaseMedia(slot, `No ${label} yet.`);
      return;
    }
    this.#releaseMedia(slot, `Loading ${label}…`);
    const view = { key, controller: new AbortController() };
    this.#views.set(slot, view);
    const status = $('#simulation-' + slot + '-state');
    const container = $('#simulation-' + slot);
    const unavailable = () => {
      if (this.#views.get(slot) !== view) return;
      this.#releaseMedia(slot, video ? 'Execution recording unavailable.' : 'Simulation frame unavailable.');
      // Retain the failed source key so unrelated state updates don't retry it.
      this.#views.set(slot, { key, controller: view.controller });
    };
    try {
      const blob = await this.#api.simulationMedia(source, video ? 'video' : 'image', view.controller.signal);
      if (this.#views.get(slot) !== view) return;
      view.url = URL.createObjectURL(blob);
      if (video) {
        const player = element('video');
        view.media = player;
        player.controls = true;
        player.playsInline = true;
        player.preload = 'metadata';
        player.setAttribute('aria-label', 'MuJoCo execution recording');
        player.addEventListener('error', unavailable, { once: true });
        player.src = view.url;
      } else {
        const image = element('img');
        view.media = image;
        image.alt = 'MuJoCo simulation frame';
        image.src = view.url;
        await image.decode();
      }
      if (this.#views.get(slot) !== view) return;
      container.replaceChildren(view.media);
      status.hidden = true;
    } catch {
      unavailable();
    }
  }

  #showSimulationMetrics(sim) {
    const metrics = $('#simulation-metrics');
    const value = words([
      sim?.scene_id,
      sim?.source_revision ? `source ${sim.source_revision}` : '',
      sim?.control_mode,
      count(sim?.frame_count, 'frames'),
      Number.isFinite(sim?.motion_seconds) ? `${sim.motion_seconds.toFixed(2)} s of motion` : '',
    ]);
    setText(metrics, value);
    metrics.hidden = !value;
    const warningList = $('#simulation-warnings');
    const warnings = list(sim?.warnings, warning => typeof warning === 'string' ? warning : '');
    const signature = JSON.stringify(warnings);
    if (signature !== this.#warningCache) {
      this.#warningCache = signature;
      warningList.replaceChildren(...warnings.map(warning => element('li', warning)));
      warningList.hidden = !warnings.length;
    }
  }

  #showActivity(snapshot, audio, task) {
    const notebook = snapshot?.notebook || [];
    const events = notebook.filter(event => traceKinds.has(event.kind)).slice(-40);
    const adapter = notebook.findLast(event => event.kind === 'expert_started' && event.task_id === task?.task_id)?.data?.adapter;
    const run = task?.expert_runs?.at(-1);
    const request = snapshot?.requests?.findLast(item => item.task_id === task?.task_id);
    const status = [
      ['Backend', snapshot?.backend],
      ['Task', humanize(task?.status) || 'No task yet'],
      ['Route', humanize(task?.route)],
      ['Voice', audio?.status || 'Voice off'],
      ['Voice model', words([audio?.provider, audio?.model || snapshot?.voice_model])],
      ['Expert', words([adapter?.provider || run?.provider, adapter?.model || run?.model, adapter?.reasoning_effort || run?.reasoning_effort]) || 'No expert run yet'],
      ['Planning time', duration(request?.metrics?.planning_ms)],
      ['Last expert run', words([duration(run?.host_elapsed_ms ?? run?.elapsed_ms), count(run?.calls, 'model calls')])],
      ['Execution', typeof snapshot?.state === 'string' ? snapshot.state : humanize(snapshot?.state?.phase || snapshot?.state?.status)],
    ];
    const statusKey = JSON.stringify(status);
    if (statusKey !== this.#statusCache) {
      this.#statusCache = statusKey;
      rows($('#developer-status'), status);
    }
    const traceKey = JSON.stringify([snapshot?.session_id, events.map(event => event.event_id || event)]);
    if (traceKey === this.#traceCache) return;
    this.#traceCache = traceKey;
    $('#trace-empty').hidden = events.length > 0;
    const trace = $('#developer-trace');
    trace.hidden = !events.length;
    trace.replaceChildren(...events.reverse().map(event => {
      const data = event.data || {};
      const adapter = data.adapter || data.run || {};
      const step = Number.isInteger(data.step) ? `step ${data.step + 1}` : '';
      const info = words([adapter.name || data.operation, data.phase, step, duration(adapter.elapsed_ms), event.provenance]);
      const label = words([traceKinds.get(event.kind), info]);
      const result = adapter.result || data.observation || data.receipt || {};
      const evidence = [...new Set([
        ...(event.evidence_ids || []),
        ...list(result.images || adapter.images, image => image.evidence_id),
      ])].join(', ');
      const item = receipt(label, [
        ['Summary', adapter.summary || result.text || result.summary || data.request?.summary],
        ['Status', result.status || data.status || data.decision?.status],
        ['Reason', data.reason || result.reason],
        ['View', adapter.arguments?.view || result.view],
        ['Requested labels', list(adapter.arguments?.labels, String).join(', ')],
        ['Verified labels', list(result.verified_labels, String).join(', ')],
        ['Tool outcome', result.valid],
        ['Model call', adapter.call],
        ['Host time', duration(adapter.host_elapsed_ms)],
        ['Evidence IDs', evidence],
        ['Task ID', event.task_id],
        ['Request ID', event.request_id],
      ]);
      const timestamp = event.timestamp ?? event.time;
      const date = typeof timestamp === 'number' ? new Date(timestamp * (timestamp < 1e12 ? 1000 : 1)) : new Date(timestamp);
      if (Number.isFinite(date.getTime())) {
        const time = element('time', date.toLocaleTimeString());
        time.dateTime = date.toISOString();
        item.querySelector('summary').prepend(time);
      }
      return item;
    }));
  }

  #showSkills(snapshot) {
    const skills = snapshot?.skills || snapshot?.active_skills || [];
    const evaluations = snapshot?.evaluations || [];
    const decisions = snapshot?.skill_decisions || [];
    const key = JSON.stringify([skills, evaluations, decisions]);
    if (key === this.#skillCache) return;
    this.#skillCache = key;
    $('#skill-evidence-empty').hidden = Boolean(skills.length || evaluations.length);
    $('#developer-skills').hidden = !skills.length;
    $('#developer-evaluations').hidden = !evaluations.length;
    $('#developer-skills').replaceChildren(...skills.map(skill => receipt(
      words([skill.name || skill.skill_id, humanize(skill.status || skill.lifecycle)]), [
        ['Version', skill.version || skill.skill_version],
        ['Skill ID', skill.skill_id],
        ['Intent', skill.intent],
        ['Limitations', list(skill.limitations, String).join(' · ')],
        ['Evidence IDs', list(skill.evidence_ids, String).join(', ')],
      ])));
    $('#developer-evaluations').replaceChildren(...evaluations.map(evaluation => {
      const decision = decisions.findLast(item => item.evaluation_id === evaluation.evaluation_id);
      const result = evaluation.passed === true ? 'Passed' : evaluation.passed === false ? 'Failed' : '';
      return receipt(words(['Evaluation receipt', result, humanize(decision?.status)]), [
        ['ID', evaluation.evaluation_id],
        ['Environment', evaluation.metrics?.environment || evaluation.metrics?.provenance],
        ['Candidate', evaluation.candidate_hash],
        ['Baseline', evaluation.baseline_hash],
        ['Candidate recoveries', evaluation.candidate_recovered],
        ['Baseline recoveries', evaluation.baseline_recovered],
        ['Reasons', list(evaluation.reasons, String).join(' · ')],
        ['Suite hash', evaluation.suite_hash],
        ['Artifact hashes', list(evaluation.artifact_hashes, String).join(', ')],
        ['Regression gates', Object.entries(evaluation.regression_gates || {}).map(([gate, passed]) => `${humanize(gate)} ${passed ? 'passed' : 'failed'}`).join(' · ')],
      ]);
    }));
  }

  render(snapshot, audio, task) {
    const sim = snapshot?.state?.simulation;
    const status = sim ? humanize(sim.status) || 'Status unavailable' : snapshot ? 'No simulation data' : 'Waiting for session';
    setText($('#simulation-status'), status);
    this.#showSimulationMetrics(sim);
    void this.#loadMedia('frame', sim?.frame_url, snapshot);
    void this.#loadMedia('video', sim?.video_url, snapshot);
    this.#showActivity(snapshot, audio, task);
    this.#showSkills(snapshot);
  }

  audio(status, snapshot, task) { this.#showActivity(snapshot, status, task); }
}
