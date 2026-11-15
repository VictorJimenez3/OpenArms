import { LABS, SOON } from './labs.js';
import { Live, thumbnail } from './live.js';

const KEY = 'openarms.student.v1';
const STEPS = ['Question', 'Predict', 'Direct Ollie', 'Observe', 'Explain'];
const view = document.getElementById('view');
const live = document.getElementById('live');
const $ = (sel, root = document) => root.querySelector(sel);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const lab = id => LABS.find(item => item.id === id);
const VARIANT = { volcano: 'volcano', potions: 'potions', lava: 'lava_lamp' };
const isLive = item => Boolean(Live.variant) && VARIANT[item.id] === Live.variant;
const kindLabel = item => item.kind === 'bench' ? 'Real bench' : isLive(item) ? 'Live simulation' : 'Simulation';
let liveRun = 0;

let store = { runs: {}, name: '' };
try { store = { ...store, ...JSON.parse(localStorage.getItem(KEY)) }; } catch { /* Storage can be unavailable. */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch { /* Keep working in memory. */ } };
const run = id => (store.runs[id] ||= { step: 0, observations: [], questions: [], pours: 0 });
const say = text => { live.textContent = ''; requestAnimationFrame(() => { live.textContent = text; }); };

const ICON = {
  mic: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  play: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M8 5l11 7-11 7z" fill="currentColor"/></svg>',
  stop: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>',
  sound: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 0 1 0 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  arrow: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  check: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};


// ---------- Ollie ----------
const ollieSVG = (pose = 'idle') => `
  <svg class="ollie-bot" data-pose="${pose}" viewBox="-50 -20 300 250" aria-hidden="true">
    <ellipse class="o-floor" cx="100" cy="220" rx="76" ry="8"/>
    <rect class="o-body" x="44" y="188" width="112" height="32" rx="16"/>
    <g class="o-shoulder">
      <rect class="o-body" x="82" y="112" width="36" height="92" rx="18"/>
      <g class="o-elbow">
        <rect class="o-body" x="84" y="50" width="32" height="86" rx="16"/>
        <g class="o-head">
          <rect class="o-body o-ear o-ear-l" x="74" y="-10" width="14" height="38" rx="7"/>
          <rect class="o-body o-ear o-ear-r" x="112" y="-10" width="14" height="38" rx="7"/>
          <rect class="o-body" x="58" y="12" width="84" height="62" rx="27"/>
          <g class="o-eyes"><circle cx="83" cy="42" r="8"/><circle cx="117" cy="42" r="8"/></g>
        </g>
        <circle class="o-joint" cx="100" cy="66" r="9"/>
      </g>
      <circle class="o-joint" cx="100" cy="124" r="11"/>
    </g>
    <circle class="o-joint" cx="100" cy="194" r="12"/>
  </svg>`;
function ollie(pose, line) {
  const bot = $('.partner .ollie-bot'), bubble = $('#bubble');
  if (bot) bot.dataset.pose = pose;
  if (bubble && bubble.textContent !== line) { bubble.textContent = line; bubble.classList.remove('pop'); void bubble.offsetWidth; bubble.classList.add('pop'); }
}
const ART = {
  'potion-pour': '<svg viewBox="0 0 160 120" aria-hidden="true"><path class="a-arc" d="M46 46C62 4 104 4 118 50" fill="none"/><path class="a-glass" d="M22 52h44l-6 56H28z"/><path class="a-pink" d="M27 76h34l-3 30H30z"/><path class="a-glass" d="M92 56h52l-7 52h-38z"/><path class="a-cream" d="M96 80h44l-4 26h-36z"/></svg>',
  volcano: '<svg viewBox="0 0 160 120" aria-hidden="true"><g class="a-foam"><circle cx="80" cy="34" r="13"/><circle cx="62" cy="40" r="10"/><circle cx="98" cy="40" r="10"/><circle cx="72" cy="20" r="9"/><circle cx="90" cy="18" r="8"/></g><path class="a-ink" d="M68 40h24v22l26 46H42l26-46z"/></svg>',
  potions: '<svg viewBox="0 0 160 120" aria-hidden="true"><circle class="a-pink a-mix-l" cx="56" cy="60" r="36"/><circle class="a-green a-mix-r" cx="104" cy="60" r="36"/><circle class="a-purple" cx="80" cy="60" r="20"/></svg>',
  lava: '<svg viewBox="0 0 160 120" aria-hidden="true"><rect class="a-ink" x="50" y="6" width="60" height="108" rx="30"/><circle class="a-red a-blob b1" cx="72" cy="92" r="11"/><circle class="a-red a-blob b2" cx="90" cy="96" r="8"/><circle class="a-red a-blob b3" cx="82" cy="88" r="14"/></svg>',
  snow: '<svg viewBox="0 0 160 120" aria-hidden="true"><g class="a-snow"><circle cx="52" cy="92" r="20"/><circle cx="84" cy="84" r="27"/><circle cx="114" cy="94" r="18"/><circle cx="70" cy="62" r="16"/><circle cx="98" cy="58" r="14"/></g></svg>',
};

// ---------- speech ----------
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let listening = null;
function wireMics(root = document) {
  root.querySelectorAll('[data-mic]').forEach(button => {
    if (!Recognition) { button.hidden = true; return; }
    if (!button.innerHTML.trim()) button.innerHTML = ICON.mic;
    button.onclick = () => {
      if (listening) { listening.stop(); return; }
      const input = document.getElementById(button.dataset.mic);
      const rec = listening = new Recognition();
      rec.lang = 'en-US'; rec.interimResults = false;
      button.classList.add('on'); button.setAttribute('aria-pressed', 'true'); say('Listening');
      rec.onresult = event => { input.value = event.results[0][0].transcript; input.dispatchEvent(new Event('input', { bubbles: true })); input.focus(); };
      rec.onerror = () => say('I could not hear that. You can type instead.');
      rec.onend = () => { listening = null; button.classList.remove('on'); button.setAttribute('aria-pressed', 'false'); };
      rec.start();
    };
  });
}
function readAloud(text) {
  if (!('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(Object.assign(new SpeechSynthesisUtterance(text), { rate: 0.95 }));
}

// ---------- shelf ----------
const status = id => {
  const r = store.runs[id];
  if (!r) return ['Not started', 'idle'];
  return r.done ? ['Report ready', 'done'] : [`Step ${r.step + 1} of ${STEPS.length}`, 'going'];
};
function shelf() {
  const tile = (item, size) => { const [label, state] = status(item.id); return `
    <li class="tile ${size}" data-theme="${item.id}">
      <a href="#/lab/${item.id}">
        <span class="tile-art">${ART[item.id]}</span>
        <span class="tag">${item.kind === 'bench' ? 'On the real bench today' : kindLabel(item)}</span>
        <strong>${esc(item.title)}</strong>
        <span class="tile-q">${esc(item.question)}</span>
        <span class="tile-foot"><span>${esc(item.idea)} · ${esc(item.time)}</span><span class="state ${state}">${esc(label)}</span></span>
      </a>
    </li>`; };
  const sizes = { 'potion-pour': 'wide', volcano: 'half', potions: 'half', lava: 'third', snow: 'third' };
  view.innerHTML = `
    <section class="hero" data-theme="potion-pour">
      <div class="hero-copy">
        <h1>You’re the scientist. Ollie’s the hands.</h1>
        <p>Ollie is a robot lab partner for students who need a hand with the reaching and pouring. You make every call: what to test, when to pour, when to stop.</p>
        <a class="btn primary big" href="#labs">Pick an experiment ${ICON.arrow}</a>
      </div>
      <div class="hero-ollie partner">
        <p class="bubble pop">Hi, I’m Ollie. Tell me what to pour.</p>
        ${ollieSVG('hello')}
      </div>
    </section>
    <section id="labs" aria-labelledby="labs-title">
      <h2 id="labs-title">Today’s experiments</h2>
      <ul class="tiles">
        ${LABS.map(item => tile(item, sizes[item.id])).join('')}
        <li class="tile third soon"><div><span class="tag">Coming next</span>${SOON.map(name => `<strong>${esc(name)}</strong>`).join('')}<span class="tile-q">More pages from the kit booklet are on the way.</span></div></li>
      </ul>
    </section>
    <ol class="how" aria-label="How a lab works">
      ${[['Predict', 'Guess what will happen.'], ['Direct', 'Tell Ollie what to pour. Nothing moves until you say yes.'], ['Observe', 'Watch, listen, and say what you noticed.'], ['Explain', 'Find out why, then take home a lab report.']].map(([t, d]) => `<li><strong>${t}</strong><span>${d}</span></li>`).join('')}
    </ol>
    <section class="ways" aria-labelledby="ways-title">
      <h2 id="ways-title">Use Ollie your way</h2>
      <p>You never need a mouse or a steady hand. Every step works with whichever of these you already use.</p>
      <ul>
        <li><strong>Your voice</strong><span>Tap a mic to speak an answer, or use your device’s voice control and say the name of any button.</span></li>
        <li><strong>A keyboard or switch</strong><span><kbd>Tab</kbd> moves, <kbd>Enter</kbd> or <kbd>Space</kbd> chooses. Nothing needs two keys at once.</span></li>
        <li><strong>Eye gaze or a head pointer</strong><span>Big, well-spaced buttons. Nothing to drag, hold down or hover over.</span></li>
        <li><strong>Your own pace</strong><span>No timers. If a plan goes stale while you decide, Ollie brings it back.</span></li>
        <li><strong>Stop, always</strong><span>Press <kbd>Esc</kbd> or the Stop button while Ollie is moving.</span></li>
      </ul>
    </section>
    <p class="credit">Experiments adapted from Smartivity’s <cite>My First Science Kit</cite>. Ollie is built by the OpenArms team.</p>`;
}

// ---------- guided lab ----------
function labView(item) {
  const r = run(item.id);
  const step = Math.min(r.step, STEPS.length - 1);
  view.innerHTML = `
    <div class="lab">
      <aside class="partner" aria-label="Ollie">
        <p id="bubble" class="bubble" role="status"></p>
        ${ollieSVG()}
      </aside>
      <div class="work">
        <div class="lab-top">
          <a class="back" href="#/">All experiments</a>
          <p class="tag">${kindLabel(item)}</p>
        </div>
        <h1>${esc(item.title)}</h1>
        <ol class="arm-steps" aria-label="Lab steps">
          ${STEPS.map((name, i) => `<li class="${i < step ? 'past' : i === step ? 'now' : ''}" ${i === step ? 'aria-current="step"' : ''}>
            <button type="button" data-goto="${i}" ${i > (r.reached ?? 0) ? 'disabled' : ''} aria-label="Step ${i + 1}, ${name}${i < step ? ', done' : i === step ? ', current step' : ''}"><span class="n" aria-hidden="true">${i < step ? ICON.check : i + 1}</span><span class="l" aria-hidden="true">${name}</span></button></li>`).join('')}
        </ol>
        <section id="stage" class="sheet"></section>
        <div class="lab-nav">
          <button id="prev" class="btn ghost" type="button" ${step === 0 ? 'hidden' : ''}>Back</button>
          <p id="hint" class="hint" role="status"></p>
          <button id="next" class="btn primary big" type="button">${step === STEPS.length - 1 ? 'Make my report' : 'Next'} ${ICON.arrow}</button>
        </div>
      </div>
    </div>`;
  const stage = $('#stage'), next = $('#next'), hint = $('#hint');
  const ready = (ok, why = '') => { next.setAttribute('aria-disabled', String(!ok)); hint.textContent = ok ? '' : why; };
  [stepQuestion, stepPredict, stepDirect, stepObserve, stepExplain][step](item, r, stage, ready);
  wireMics(view);
  stage.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.matches('input[type=text]') && !e.target.closest('form')) { e.preventDefault(); next.click(); } });
  view.querySelectorAll('[data-goto]').forEach(b => b.onclick = () => goto(item, +b.dataset.goto));
  $('#prev').onclick = () => goto(item, step - 1);
  next.onclick = () => {
    if (next.getAttribute('aria-disabled') === 'true') { hint.classList.remove('nudge'); void hint.offsetWidth; hint.classList.add('nudge'); say(hint.textContent); return; }
    if (step === STEPS.length - 1) { r.done = true; r.finishedAt = new Date().toISOString(); save(); location.hash = `#/report/${item.id}`; }
    else goto(item, step + 1);
  };
}
function goto(item, step) {
  const r = run(item.id);
  if (liveRun) { liveRun = 0; Live.stop().catch(() => {}); }
  $('video', view)?.pause();
  r.step = step; r.reached = Math.max(r.reached ?? 0, step); save();
  labView(item);
  $('#stage h2')?.focus();
  window.scrollTo({ top: 0 });
}
const choices = (name, list, picked, type = 'radio') => `<div class="choices">${list.map((text, i) => `
  <label class="choice"><input type="${type}" name="${name}" value="${esc(text)}" ${(type === 'radio' ? picked === text : picked?.includes(text)) ? 'checked' : ''}><span class="mark" aria-hidden="true">${ICON.check}</span><span>${esc(text)}</span></label>`).join('')}</div>`;
const ownWords = (id, label, value) => `
  <label class="own" for="${id}">${label}</label>
  <div class="field-row"><input id="${id}" type="text" autocomplete="off" value="${esc(value)}" placeholder="Type or tap the mic"><button class="btn ghost icon mic" type="button" data-mic="${id}" aria-label="Speak your answer" aria-pressed="false"></button></div>`;

function stepQuestion(item, r, stage, ready) {
  stage.innerHTML = `
    <h2 tabindex="-1">${esc(item.question)}</h2>
    <p class="lede">${esc(item.setup)}</p>
    <dl class="facts">
      <div><dt>Big idea</dt><dd>${esc(item.idea)}</dd></div>
      <div><dt>Ollie’s job</dt><dd>${esc(item.command)}</dd></div>
      <div><dt>Your job</dt><dd>Predict, direct, observe and explain</dd></div>
    </dl>
    ${item.kind === 'bench' ? '<p class="note">This lab uses real liquids. Your teacher sets up the bench and stays with you.</p>' : isLive(item) ? '<p class="note">This lab runs live in a computer simulation. Ollie’s AI plans the pour from your words and a camera checks the result. It is a model, not a real pour.</p>' : '<p class="note">This lab plays a recorded computer simulation of the arm. It is a model, not a real pour.</p>'}`;
  ollie('idle', item.kind === 'bench' ? 'Real liquids today. I’ll do the lifting, you make the calls.' : 'Here’s today’s question. Ready when you are, scientist.');
  ready(true);
}

function stepPredict(item, r, stage, ready) {
  stage.innerHTML = `
    <h2 tabindex="-1">What do you think will happen?</h2>
    <fieldset><legend class="sr">Your prediction</legend>${choices('prediction', item.predictions, r.prediction)}</fieldset>
    ${ownWords('pred-own', 'Or say it in your own words', r.predictionOwn)}`;
  const check = () => ready(Boolean(r.prediction || r.predictionOwn), 'Pick a prediction or say your own.');
  stage.onchange = e => { if (e.target.name === 'prediction') { r.prediction = e.target.value; save(); check(); } };
  $('#pred-own').oninput = e => { r.predictionOwn = e.target.value.trim(); save(); check(); };
  ollie('think', 'What do you think will happen? There’s no wrong guess. Scientists guess first, then test.');
  check();
}

function stepDirect(item, r, stage, ready) {
  const done = () => ready(r.pours > 0, 'Ollie has not poured yet.');
  if (item.kind === 'bench') {
    stage.innerHTML = `
      <h2 tabindex="-1">Tell Ollie to pour</h2>
      <p class="lede">On the bench screen, press Talk and say:</p>
      <p class="sayit">“${esc(item.command)}”</p>
      <ol class="flow">
        <li>Ollie repeats the plan back to you.</li>
        <li>You say yes, or change it.</li>
        <li>Your teacher lets the arm move.</li>
        <li>Say “stop” or press Stop at any time.</li>
      </ol>
      <div class="actions">
        <a class="btn primary" href="/" target="_blank" rel="noopener">Open the bench screen ${ICON.arrow}</a>
        <button id="poured" class="btn ghost" type="button" aria-pressed="${r.pours > 0}">${r.pours > 0 ? 'Pour marked as done' : 'The pour is done'}</button>
      </div>`;
    ollie('listen', 'I’m at the bench. Say it out loud and I’ll repeat my plan back.');
    $('#poured').onclick = () => { r.pours = 1; r.command = item.command; save(); done(); $('#poured').textContent = 'Pour marked as done'; $('#poured').setAttribute('aria-pressed', 'true'); say('Pour marked as done.'); };
    return done();
  }
  if (isLive(item)) return liveDirect(item, r, stage, ready, done);
  const ask = note => {
    stage.innerHTML = `
      <h2 tabindex="-1">Tell Ollie what to do</h2>
      <p class="lede">${esc(item.setup)}</p>
      <form id="cmd" class="cmd">
        <label for="cmd-input">Your instruction</label>
        <div class="field-row"><input id="cmd-input" type="text" autocomplete="off" value="${esc(r.command)}" placeholder="Type or tap the mic"><button class="btn ghost icon mic" type="button" data-mic="cmd-input" aria-label="Speak your instruction" aria-pressed="false"></button><button class="btn primary" type="submit">Send</button></div>
        <button id="suggest" class="btn link" type="button">Use “${esc(item.command)}”</button>
      </form>
      ${r.pours > 0 ? `<p class="muted">Ollie has poured ${r.pours} time${r.pours > 1 ? 's' : ''}. You can pour again or go on.</p>` : ''}`;
    wireMics(stage);
    ollie(note?.startsWith('Stopped') ? 'stop' : 'listen', note || (r.pours > 0 ? 'Want another pour? Tell me, or go on to the next step.' : 'Tell me what to do. I’m listening.'));
    $('#suggest').onclick = () => { $('#cmd-input').value = item.command; $('#cmd-input').focus(); };
    $('#cmd').onsubmit = event => {
      event.preventDefault();
      const text = $('#cmd-input').value.trim();
      if (!text) return ask('I did not catch an instruction. Tell me what to pour.');
      r.command = text; save();
      const again = /\b(again|redo|repeat|one more)\b/i.test(text);
      const known = again || /\b(pour|add|tip|mix|put|empty|dump|drop)\b/i.test(text);
      propose(known ? '' : `In this lab I can do one thing: ${item.command[0].toLowerCase() + item.command.slice(1)}. Is that what you want?`, again);
    };
    done();
  };
  const propose = (clarify, again) => {
    stage.innerHTML = `
      <h2 tabindex="-1">Check Ollie’s plan</h2>
      <p class="you"><b>You</b> ${esc(r.command)}</p>
      <div class="plan">
        <p class="plan-label">${r.pours > 0 || again ? 'Ollie’s plan · saved skill' : 'Ollie’s plan'}</p>
        <p class="plan-text">${esc(item.proposal)}</p>
        <div class="actions">
          <button id="yes" class="btn primary big" type="button">Yes, do it</button>
          <button id="change" class="btn ghost" type="button">Change it</button>
          <button id="hear" class="btn ghost" type="button">${ICON.sound} Read it to me</button>
        </div>
      </div>
      <p class="muted">Nothing moves until you say yes.</p>`;
    $('#yes').onclick = play; $('#change').onclick = () => { ask(); $('#cmd-input').focus(); };
    $('#hear').onclick = () => readAloud(item.proposal);
    $('#stage h2').focus(); ready(r.pours > 0, 'Say yes to the plan, or change it.');
    ollie('think', clarify || (r.pours > 0 || again ? 'I remember this one. Same plan as before. Say yes and I’ll go.' : 'Here’s my plan. I won’t move until you say yes.'));
  };
  const play = () => {
    stage.innerHTML = `
      <h2 tabindex="-1">Ollie is pouring</h2>
      <div class="actions"><button id="stop" class="btn stop big" type="button">${ICON.stop} Stop</button><p id="run-state" class="muted" role="status">Ollie is moving.</p></div>
      <figure class="screen">
        <video src="media/${item.media}.mp4" poster="media/${item.media}.jpg" playsinline muted preload="auto"></video>
        <figcaption><span class="tag sim">Recorded simulation</span> A computer model of the arm and the reaction.</figcaption>
      </figure>`;
    const video = $('video', stage);
    ollie('pour', 'Pouring. Say stop any time.');
    say('Ollie is pouring. Press Stop or Escape to stop.');
    $('#stop').onclick = () => { video.pause(); ask('Stopped. I will not move again until you give me a new instruction.'); $('#stage h2').focus(); };
    video.onended = () => {
      r.pours += 1; save(); done();
      $('.actions', stage).innerHTML = `<button id="again" class="btn ghost" type="button">${ICON.play} Do it again</button><p class="muted" role="status">Done. Ollie is back home.</p>`;
      $('#again').onclick = () => { r.command = 'Do it again'; save(); propose('', true); };
      ollie('wave', 'Done! I’m back home. What did you notice?');
    };
    video.play().catch(() => { video.controls = true; });
    $('#stop').focus(); ready(r.pours > 0, 'Wait for Ollie to finish, or press Stop.');
  };
  ask();
}


// ---------- live simulation: the real agent plans, the simulator runs ----------
const PHASES = [[/^pick/, 'Picking up'], [/^pour/, 'Pouring'], [/^return/, 'Putting it back'], [/^home/, 'Going home'], [/inspect|observe|check/, 'Looking at the bench']];
const phaseText = phase => (PHASES.find(([re]) => re.test(phase || '')) || [0, 'Getting ready'])[1];
const DONE = ['completed', 'failed', 'cancelled', 'stopped', 'expired', 'unknown', 'needs_clarification'];
const seconds = ms => `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
function planFacts(metrics = {}) {
  const saved = metrics.dispatch === 'active_skill';
  return {
    saved, seconds: metrics.planning_ms ? seconds(metrics.planning_ms) : '', calls: metrics.model_calls ?? null,
    label: saved ? 'Saved skill' : 'New plan',
    text: [saved ? 'Ollie already knew this one' : 'Ollie worked this out just now', metrics.planning_ms ? `planned in ${seconds(metrics.planning_ms)}` : '', metrics.model_calls != null ? `${metrics.model_calls} AI expert call${metrics.model_calls === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · '),
  };
}
function liveDirect(item, r, stage, ready, done) {
  const token = ++liveRun;
  const here = () => token === liveRun && stage.isConnected;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const fail = error => { if (here()) ask(`Something went wrong: ${error.message} Try again.`, 'stop'); };
  let frameUrl = '', objectUrl = '', stale = false;
  const showFrame = async (state, img) => {
    const url = state.state?.simulation?.frame_url;
    if (!url || url === frameUrl || !img) return;
    frameUrl = url;
    try { const next = URL.createObjectURL(await Live.blob(url)); img.src = next; img.hidden = false; URL.revokeObjectURL(objectUrl); objectUrl = next; } catch { /* Keep the last picture. */ }
  };
  const bench = caption => `
      <figure class="screen live">
        <img id="live-frame" alt="Live camera view of the simulated bench" hidden>
        <figcaption><span class="tag sim">Live simulation</span> <span id="live-caption">${esc(caption)}</span></figcaption>
      </figure>`;

  const ask = (note, pose) => {
    stage.innerHTML = `
      <h2 tabindex="-1">Tell Ollie what to do</h2>
      <p class="lede">${esc(item.setup)}</p>
      <form id="cmd" class="cmd">
        <label for="cmd-input">Your instruction</label>
        <div class="field-row"><input id="cmd-input" type="text" autocomplete="off" value="" placeholder="Type or tap the mic"><button class="btn ghost icon mic" type="button" data-mic="cmd-input" aria-label="Speak your instruction" aria-pressed="false"></button><button class="btn primary" type="submit">Send</button></div>
        <button id="suggest" class="btn link" type="button">Use “${esc(item.command)}”</button>
      </form>
      ${r.pours > 0 ? `<p class="muted">Ollie has poured ${r.pours} time${r.pours > 1 ? 's' : ''}. Say “do it again” to see how fast a saved skill is, or go on.</p>` : '<p class="muted">Say it your own way. Ollie’s AI reads your words, looks at the bench and makes a plan.</p>'}`;
    wireMics(stage);
    ollie(pose || 'listen', note || (r.pours > 0 ? 'Want another pour? Tell me, or go on to the next step.' : 'Tell me what to do. I’m listening.'));
    $('#suggest').onclick = () => { $('#cmd-input').value = item.command; $('#cmd-input').focus(); };
    $('#cmd').onsubmit = event => {
      event.preventDefault();
      const text = $('#cmd-input').value.trim();
      if (!text) return ollie('listen', 'I did not catch an instruction. Tell me what to pour.');
      r.command = text; save();
      plan(text).catch(fail);
    };
    done();
  };

  const plan = async (text, note) => {
    const started = performance.now();
    stage.innerHTML = `
      <h2 tabindex="-1">Ollie is making a plan</h2>
      <p class="you"><b>You</b> ${esc(text)}</p>
      ${bench('Ollie is looking at the bench.')}
      <div class="actions"><button id="never" class="btn ghost" type="button">Never mind</button><p id="clock" class="muted" role="status"></p></div>`;
    ollie('think', 'Let me look at the bench and work out a plan.');
    $('#stage h2').focus(); ready(false, 'Ollie is still planning.');
    let cancelled = false;
    $('#never').onclick = () => { cancelled = true; Live.cancel().catch(() => {}); ask('No problem. Nothing moved.'); };
    const before = await Live.fresh();
    if (!here() || cancelled) return;
    showFrame(before, $('#live-frame'));
    const known = (before.messages || []).length;
    let state = await Live.ask(text);
    while (here() && !cancelled) {
      const task = (state.tasks || []).at(-1);
      if (state.pending) return propose(state.pending, note);
      if (task && DONE.includes(task.status)) {
        const reply = (state.messages || []).slice(known).filter(m => m.role === 'assistant').at(-1)?.text;
        return ask(reply || 'I could not make a plan for that. Try saying it another way.', 'think');
      }
      const waited = (performance.now() - started) / 1000;
      if ($('#clock')) $('#clock').textContent = waited > 3 ? `Thinking for ${Math.round(waited)} s. New instructions take Ollie longer the first time.` : '';
      await wait(600);
      state = await Live.state();
    }
  };

  const propose = async (pending, note) => {
    const facts = planFacts(pending.metrics);
    stage.innerHTML = `
      <h2 tabindex="-1">Check Ollie’s plan</h2>
      <p class="you"><b>You</b> ${esc(r.command)}</p>
      <div class="plan">
        <p class="plan-label">Ollie’s plan · ${facts.label}</p>
        <p class="plan-text">${esc(pending.summary)}</p>
        <p class="plan-facts">${esc(facts.text)}</p>
        <div class="actions">
          <button id="yes" class="btn primary big" type="button">Yes, do it</button>
          <button id="change" class="btn ghost" type="button">Change it</button>
          <button id="hear" class="btn ghost" type="button">${ICON.sound} Read it to me</button>
        </div>
      </div>
      <p class="muted">Nothing moves until you say yes.</p>`;
    ollie('think', note || (facts.saved ? 'I remember this one! Same plan as before. Say yes and I’ll go.' : 'Here’s my plan. I won’t move until you say yes.'));
    if (!note) stale = false;
    $('#stage h2').focus(); ready(r.pours > 0, 'Say yes to the plan, or change it.');
    $('#hear').onclick = () => readAloud(pending.summary);
    $('#change').onclick = () => { Live.cancel(pending).catch(() => {}); ask('Okay, I dropped that plan. What should I do instead?'); $('#cmd-input').focus(); };
    $('#yes').onclick = () => {
      $('#yes').disabled = true;
      execute(pending, facts).catch(error => {
        if (!here()) return;
        if (![400, 409, 410].includes(error.status) || stale) return fail(error);
        stale = true; // The plan went stale while the student decided: ask for the same thing again.
        plan(r.command, 'That plan went stale while you were deciding, so I made it again. Take your time.').catch(fail);
      });
    };
    await Live.present(pending).catch(() => {});
  };

  const execute = async (pending, facts) => {
    let state = await Live.confirm(pending);
    if (!here()) return;
    stage.innerHTML = `
      <h2 tabindex="-1">Ollie is pouring</h2>
      <div class="actions"><button id="stop" class="btn stop big" type="button">${ICON.stop} Stop</button><p id="run-state" class="muted" role="status">Ollie is moving.</p></div>
      ${bench('Getting ready')}`;
    ollie('pour', 'On it. Say stop any time.');
    say('Ollie is pouring. Press Stop or Escape to stop.');
    $('#stop').focus(); ready(r.pours > 0, 'Wait for Ollie to finish, or press Stop.');
    let stopped = false;
    $('#stop').onclick = async () => { stopped = true; await Live.stop().catch(() => {}); if (here()) ask('Stopped. I will not move again until you give me a new instruction.', 'stop'); };
    const img = $('#live-frame'), caption = $('#live-caption');
    while (here() && !stopped) {
      const task = (state.tasks || []).find(t => t.task_id === pending.task_id) || {};
      showFrame(state, img);
      if (caption) caption.textContent = phaseText(state.state?.phase);
      if (DONE.includes(task.status)) return finish(state, task, pending, facts);
      await wait(350);
      state = await Live.state();
    }
  };

  const finish = async (state, task, pending, facts) => {
    const seen = (state.observations || []).filter(o => o.request_id === pending.request_id).at(-1);
    if (task.status !== 'completed' || !seen) return ask(seen?.reason || 'That run did not finish, so I have nothing to report. Want to try again?', 'stop');
    const sim = state.state?.simulation || {};
    let picture = '';
    try { picture = await thumbnail(await Live.blob(seen.receipt?.images?.[0]?.artifact_url || sim.frame_url)); } catch { /* The words are the evidence that matters. */ }
    r.pours += 1;
    r.live = { observation: seen.text, readable: seen.status === 'observed', picture, plan: pending.summary, facts: facts.text, saved: facts.saved, motion: sim.motion_seconds ? `${Math.round(sim.motion_seconds)} s` : '', expert: Live.expert };
    (r.attempts ||= []).push({ command: r.command, label: facts.label, seconds: facts.seconds, calls: facts.calls });
    save(); done();
    if (!here()) return;
    stage.innerHTML = `
      <h2 tabindex="-1">Done. Ollie is back home.</h2>
      <figure class="screen live">
        ${sim.video_url ? '<video id="replay" playsinline muted controls></video>' : `<img src="${picture}" alt="The bench after the pour">`}
        <figcaption><span class="tag sim">Live simulation</span> ${sim.video_url ? 'Replay of the run you just directed.' : 'The bench after the pour.'}</figcaption>
      </figure>
      <p class="ollie"><b>Ollie · checked with the camera</b> ${esc(seen.text)}</p>
      ${attemptsTable(r)}
      <div class="actions"><button id="again" class="btn ghost" type="button">${ICON.play} Do it again</button></div>`;
    ollie('wave', 'Done! I’m back home. What did you notice?');
    $('#stage h2').focus();
    $('#again').onclick = () => { r.command = 'Do it again'; save(); plan('Do it again').catch(fail); };
    if (sim.video_url) Live.blob(sim.video_url).then(blob => { const video = $('#replay'); if (video) { video.src = URL.createObjectURL(blob); video.play().catch(() => {}); } }).catch(() => {});
  };
  ask();
}
const attemptsTable = r => (r.attempts || []).length < 2 ? '' : `
  <table class="attempts"><caption>How Ollie planned each try</caption>
    <thead><tr><th scope="col">You said</th><th scope="col">Plan</th><th scope="col">Time to plan</th><th scope="col">AI expert calls</th></tr></thead>
    <tbody>${r.attempts.map(a => `<tr><td>${esc(a.command)}</td><td>${esc(a.label)}</td><td>${esc(a.seconds || '—')}</td><td>${a.calls ?? '—'}</td></tr>`).join('')}</tbody></table>`;

function stepObserve(item, r, stage, ready) {
  stage.innerHTML = `
    <h2 tabindex="-1">What did you notice?</h2>
    ${item.kind === 'sim' ? `
    <div class="result">
      <img src="${r.live?.picture || `media/${item.media}.jpg`}" alt="" width="320" height="180">
      <div><p class="plan-label">${r.live ? 'Ollie’s description · checked with the simulation camera' : 'Ollie’s description · from the simulation'}</p><p>${esc(r.live?.observation || item.result)}</p>
      <button id="hear" class="btn ghost" type="button">${ICON.sound} Read it to me</button></div>
    </div>` : '<p class="lede">Look at cup C. If it is hard to see, ask Ollie or your teacher to describe it in words.</p>'}
    <fieldset><legend>Tick everything you noticed</legend>${choices('obs', item.observations, r.observations, 'checkbox')}</fieldset>
    ${ownWords('obs-own', 'Anything else, in your own words', r.observationOwn)}`;
  const check = () => ready(Boolean(r.observations.length || r.observationOwn), 'Tick what you noticed or say it in your own words.');
  ollie('listen', item.kind === 'sim' ? 'Tell me what you noticed. I can read my description out loud too.' : 'Tell me what you noticed. Ask if you want it described in words.');
  if ($('#hear')) $('#hear').onclick = () => readAloud(r.live?.observation || item.result);
  stage.onchange = e => { if (e.target.name === 'obs') { r.observations = [...stage.querySelectorAll('[name=obs]:checked')].map(i => i.value); save(); check(); } };
  $('#obs-own').oninput = e => { r.observationOwn = e.target.value.trim(); save(); check(); };
  check();
}

const predictionText = r => [r.prediction, r.predictionOwn].filter(Boolean).join('. ');
const observationText = r => [...r.observations, r.observationOwn].filter(Boolean).join('. ');
function stepExplain(item, r, stage, ready) {
  const picked = item.check.options.find(o => o.text === r.checkAnswer);
  stage.innerHTML = `
    <h2 tabindex="-1">Why did that happen?</h2>
    <dl class="compare">
      <div><dt>You predicted</dt><dd>${esc(predictionText(r))}</dd></div>
      <div><dt>You noticed</dt><dd>${esc(observationText(r))}</dd></div>
    </dl>
    <fieldset><legend>Did your prediction match?</legend>${choices('match', ['Yes', 'Partly', 'No'], r.match)}</fieldset>
    <p class="explain">${esc(item.explain)}</p>
    <fieldset><legend>${esc(item.check.ask)}</legend>${choices('check', item.check.options.map(o => o.text), r.checkAnswer)}
      <p id="feedback" class="feedback ${picked ? (picked.right ? 'right' : 'retry') : ''}" role="status">${picked ? esc(picked.why) + (picked.right ? '' : ' Try another answer.') : ''}</p></fieldset>
    <fieldset><legend>You are the scientist. What would you test next?</legend>${choices('next', item.next, r.next)}</fieldset>
    ${ownWords('next-own', 'Or your own idea', r.nextOwn)}`;
  const check = () => ready(Boolean(r.match && r.checkAnswer), 'Answer the two questions above to finish.');
  ollie(picked?.right ? 'wave' : 'idle', 'Here’s why that happened. Then you pick what we test next.');
  stage.onchange = e => {
    if (e.target.name === 'match') r.match = e.target.value;
    if (e.target.name === 'next') r.next = e.target.value;
    if (e.target.name === 'check') {
      r.checkAnswer = e.target.value; r.checkTries = (r.checkTries || 0) + 1;
      const o = item.check.options.find(x => x.text === r.checkAnswer), f = $('#feedback');
      f.className = `feedback ${o.right ? 'right' : 'retry'}`; f.textContent = o.why + (o.right ? '' : ' Try another answer.');
      ollie(o.right ? 'wave' : 'think', o.right ? 'Nailed it, scientist.' : 'Not quite. Have another go.');
    }
    save(); check();
  };
  $('#next-own').oninput = e => { r.nextOwn = e.target.value.trim(); save(); };
  check();
}

// ---------- report ----------
function reportRows(item, r) {
  const answer = item.check.options.find(o => o.text === r.checkAnswer);
  return [
    ['Question', item.question],
    ['Setup', item.setup],
    ['My prediction', predictionText(r)],
    ['What I told Ollie', (r.attempts || []).map(a => `“${a.command}”`).join(', then ') || r.command || item.command],
    ['What Ollie did', r.live ? `${r.live.plan} Poured ${r.pours} time${r.pours > 1 ? 's' : ''}.` : `${item.proposal.replace(/^I will/, 'Ollie agreed to')} Poured ${r.pours || 1} time${r.pours > 1 ? 's' : ''}.`],
    ...(r.live ? [['How Ollie planned it', (r.attempts || []).map((a, i) => `Try ${i + 1}: ${a.label.toLowerCase()}${a.seconds ? ', ' + a.seconds : ''}${a.calls != null ? `, ${a.calls} AI expert call${a.calls === 1 ? '' : 's'}` : ''}`).join('. ') + '.']] : []),
    ['What I noticed', observationText(r)],
    ...(item.kind === 'sim' ? [['Ollie’s description', r.live?.observation || item.result]] : []),
    ['Did my prediction match?', r.match],
    ['Why it happened', item.explain],
    [item.check.ask, `${r.checkAnswer}${answer?.right ? '' : ' (not the expected answer)'}`],
    ['What I would test next', [r.next, r.nextOwn].filter(Boolean).join('. ') || 'Not chosen yet'],
    ...(r.questions.length ? [['Questions I still have', r.questions.join(' · ')]] : []),
  ];
}
function report(item) {
  const r = run(item.id);
  if (!r.done) { location.hash = `#/lab/${item.id}`; return; }
  const rows = reportRows(item, r);
  const date = new Date(r.finishedAt || Date.now()).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  const evidence = r.live ? 'Live MuJoCo simulation, planned by Ollie’s AI and checked by camera' : item.kind === 'sim' ? 'Recorded simulation (computer model)' : 'Real bench, observed by the student';
  view.innerHTML = `
    <article class="report">
      <div class="lab-top no-print"><a class="back" href="#/">All experiments</a></div>
      <header>
        <div class="stamp" aria-hidden="true">${ollieSVG('wave')}<span>Hands by Ollie</span></div>
        <h1>Lab report: ${esc(item.title)}</h1>
        <div class="report-meta">
          <label for="name" class="no-print">Scientist</label>
          <input id="name" type="text" autocomplete="name" value="${esc(store.name)}" placeholder="Your name">
          <span>${esc(date)}</span><span>Evidence: ${esc(evidence)}</span>
        </div>
      </header>
      ${r.live?.picture ? `<figure class="report-pic"><img src="${r.live.picture}" alt="The simulated bench after the pour"><figcaption>The bench after the pour · simulation camera</figcaption></figure>` : ''}
      <dl class="report-rows">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      <p class="credit">Experiment adapted from Smartivity’s <cite>My First Science Kit</cite>, ${esc(item.pages)}. Robot actions by Ollie, the OpenArms lab arm, directed by the student.</p>
      <div class="actions no-print">
        <button id="print" class="btn primary" type="button">Print or save as PDF</button>
        <button id="copy" class="btn ghost" type="button">Copy for my teacher</button>
        <button id="redo" class="btn ghost" type="button">Run this lab again</button>
      </div>
    </article>`;
  $('#name').oninput = e => { store.name = e.target.value; save(); };
  $('#print').onclick = () => window.print();
  $('#copy').onclick = async () => {
    const text = [`Lab report: ${item.title}`, `Scientist: ${store.name || '—'} · ${date}`, `Evidence: ${evidence}`, '', ...rows.map(([k, v]) => `${k}: ${v}`)].join('\n');
    try { await navigator.clipboard.writeText(text); $('#copy').textContent = 'Copied'; say('Report copied.'); } catch { $('#copy').textContent = 'Copy is blocked here. Use Print instead.'; }
  };
  $('#redo').onclick = () => { if (confirm('Start this lab again? Your current report will be replaced.')) { delete store.runs[item.id]; save(); location.hash = `#/lab/${item.id}`; } };
}
function reports() {
  const done = LABS.filter(item => store.runs[item.id]?.done);
  view.innerHTML = `
    <section class="intro"><h1>My reports</h1></section>
    ${done.length ? `<ul class="labs">${done.map(item => `<li><a class="lab-row" href="#/report/${item.id}">
      <span class="lab-main"><strong>${esc(item.title)}</strong><span>${esc(item.question)}</span></span>
      <span class="lab-meta"><span>${esc(item.idea)}</span><span>${new Date(store.runs[item.id].finishedAt).toLocaleDateString()}</span></span>
      <span class="state done">Open report</span></a></li>`).join('')}</ul>`
    : `<div class="empty"><p>No reports yet. Finish an experiment and your report shows up here, ready to print for your teacher.</p><a class="btn primary" href="#/">Pick an experiment ${ICON.arrow}</a></div>`}`;
}

// ---------- Ask Ollie ----------
const GENERAL = [
  { q: 'Who is Ollie?', a: 'I am the robot arm in the OpenArms lab. You make the science choices. I do the reaching, lifting and pouring.' },
  { q: 'What can Ollie do?', a: 'I can pick up a cup, pour it into another one, and put it back. I always tell you my plan first and wait for your yes.' },
  { q: 'How do I stop Ollie?', a: 'Press Stop or say “stop”. I stop right away and I do not start again until you give me a new instruction.' },
];
const askPanel = $('#ask'), askLog = $('#ask-log');
let askLab = null;
function refreshAsk() {
  const list = askLab ? askLab.ask : GENERAL;
  $('#ask-scope').textContent = askLab ? `About ${askLab.title}. Answers come from the lab guide.` : 'Answers come from the lab guide.';
  $('#ask-chips').innerHTML = list.map((item, i) => `<button class="chip" type="button" data-q="${i}">${esc(item.q)}</button>`).join('');
  $('#ask-chips').querySelectorAll('[data-q]').forEach(b => b.onclick = () => turn(list[b.dataset.q].q, list[b.dataset.q].a));
  $('#ask-form label').textContent = askLab ? 'A question of your own' : 'A question of your own (open a lab to save it to a report)';
}
function turn(q, a) {
  askLog.insertAdjacentHTML('beforeend', `<p class="you"><b>You</b> ${esc(q)}</p><p class="ollie"><b>Ollie</b> ${esc(a)}</p>`);
  askLog.scrollTop = askLog.scrollHeight;
}
function toggleAsk(open) {
  askPanel.hidden = !open; document.body.classList.toggle('asking', open);
  $('#ask-open').setAttribute('aria-expanded', String(open));
  if (open) { refreshAsk(); $('#ask-close').focus(); } else $('#ask-open').focus();
}
$('#ask-open').onclick = () => toggleAsk(askPanel.hidden);
$('#ask-close').onclick = () => toggleAsk(false);
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const stop = document.getElementById('stop');
  if (stop) { e.preventDefault(); stop.click(); } else if (!askPanel.hidden) toggleAsk(false);
});
$('#ask-form').onsubmit = event => {
  event.preventDefault();
  const input = $('#ask-input'), text = input.value.trim();
  if (!text) return;
  if (askLab) { run(askLab.id).questions.push(text); save(); }
  turn(text, askLab ? 'Good question. I can only answer from the lab guide right now, so I saved it to your report for you and your teacher.' : 'Good question. I can only answer from the lab guide right now. Open a lab and I can save questions to your report.');
  input.value = '';
};

// ---------- router ----------
function route() {
  if (location.hash && !location.hash.startsWith('#/')) { document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }); if (view.childElementCount) return; }
  const [, page, id] = location.hash.split('/');
  const item = lab(id);
  speechSynthesis?.cancel();
  askLab = (page === 'lab' || page === 'report') && item ? item : null;
  if (!askPanel.hidden) refreshAsk();
  document.querySelectorAll('[data-nav]').forEach(a => a.toggleAttribute('aria-current', a.dataset.nav === (page === 'reports' || page === 'report' ? 'reports' : 'shelf')));
  if (page === 'lab' && item) labView(item);
  else if (page === 'report' && item) report(item);
  else if (page === 'reports') reports();
  else shelf();
  const anchored = location.hash && !location.hash.startsWith('#/');
  document.body.dataset.theme = page === 'lab' && item ? item.id : '';
  document.title = `${askLab ? askLab.title + ' · ' : ''}Ollie by OpenArms`;
  if (!anchored) window.scrollTo({ top: 0 });
}
addEventListener('hashchange', () => { route(); if (!location.hash.startsWith('#/')) return; view.focus({ preventScroll: true }); });
wireMics();
await Promise.race([Live.init(), new Promise(resolve => setTimeout(resolve, 2500))]);
route();
