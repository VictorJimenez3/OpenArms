// Showcase interactions: userflow stepper + screenshot tabs. No backend, no APIs.

const FLOW = [
  {
    title: 'A question, in the student\u2019s words',
    body: 'Each lab opens with a real question \u2014 \u201cWhat happens when a sour liquid meets baking soda?\u201d The student reads it, hears it read aloud, or has Ollie explain it. No prior knowledge is assumed.',
    who: 'Student drives \u00b7 Ollie assists',
    pose: 'listen',
  },
  {
    title: 'The student predicts first',
    body: 'Before anything moves, the student commits to what they think will happen. Wrong predictions are part of the science \u2014 Ollie answers with \u201cNot quite. Have another go.\u201d',
    who: 'Student decides \u00b7 Ollie waits',
    pose: 'think',
  },
  {
    title: 'Direct Ollie \u2014 plan, then permission',
    body: 'The student asks for an action in their own words. Ollie replies with one bounded action and its exact plan: which cup, which direction, where it returns. Nothing moves until the student confirms that exact version.',
    who: 'Student authorizes each action',
    pose: 'idle',
  },
  {
    title: 'Observe what actually happened',
    body: 'After the action, a fresh camera frame is checked independently of what the controller reported. The student records what they saw \u2014 and the app says UNKNOWN rather than guess when it can\u2019t tell.',
    who: 'Independent observer reports',
    pose: 'listen',
  },
  {
    title: 'Explain it \u2014 the student owns the science',
    body: 'A short check and a follow-up question close the loop. The student writes the conclusion in their own words, and the app generates a printable lab report for their teacher.',
    who: 'Student concludes \u00b7 report is theirs',
    pose: 'wave',
  },
];

const SHOTS = {
  'lab-question':   { src: 'assets/shots/lab-question.png',   alt: 'The Ollie student app showing the lab question step',            cap: 'Step 1 \u00b7 The question, with Ollie beside it.' },
  'lab-predict':    { src: 'assets/shots/lab-predict.png',    alt: 'The Predict step with answer choices',                          cap: 'Step 2 \u00b7 The student predicts before anything moves.' },
  'lab-plan':       { src: 'assets/shots/lab-plan.png',       alt: 'Ollie\u2019s plan card asking for confirmation',                 cap: 'Step 3 \u00b7 The exact plan, waiting for a yes.' },
  'lab-observe-done': { src: 'assets/shots/lab-observe-done.png', alt: 'The Observe step after the simulated pour finished',      cap: 'Step 4 \u00b7 What did you actually see?' },
  'lab-explain':    { src: 'assets/shots/lab-explain.png',    alt: 'The Explain step with comprehension checks',                   cap: 'Step 5 \u00b7 The student explains what happened.' },
  'report':         { src: 'assets/shots/report.png',         alt: 'The generated lab report ready to print',                      cap: 'Report \u00b7 Printable, with the evidence source stated.' },
};

// ---------- userflow stepper ----------
const stepButtons = [...document.querySelectorAll('#flowSteps [data-step]')];
const fdTitle = document.getElementById('fdTitle');
const fdBody = document.getElementById('fdBody');
const fdWho = document.getElementById('fdWho');
const detailBox = document.getElementById('flowDetail');

function showStep(i) {
  const d = FLOW[i];
  stepButtons.forEach((b, j) => {
    if (j === i) b.setAttribute('aria-current', 'step');
    else b.removeAttribute('aria-current');
  });
  fdTitle.textContent = d.title;
  fdBody.textContent = d.body;
  fdWho.textContent = d.who;
  const bot = document.querySelector('.flow-detail .ollie-bot') || document.querySelector('.consent-band .ollie-bot');
  if (bot) bot.dataset.pose = d.pose;
}

stepButtons.forEach((b) => {
  b.addEventListener('click', () => showStep(Number(b.dataset.step)));
});

// Auto-advance the stepper while the section is on screen; stops on interaction or reduced motion.
const flowSection = document.getElementById('flow');
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
let autoTimer = null, autoIndex = 0, userTouched = false;

stepButtons.forEach((b) => b.addEventListener('click', () => { userTouched = true; clearInterval(autoTimer); }, { once: true }));

if ('IntersectionObserver' in window && !reduceMotion) {
  const io = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !userTouched) {
      if (!autoTimer) {
        autoTimer = setInterval(() => {
          autoIndex = (autoIndex + 1) % FLOW.length;
          showStep(autoIndex);
        }, 4200);
      }
    } else if (autoTimer) {
      clearInterval(autoTimer);
      autoTimer = null;
    }
  }, { threshold: 0.35 });
  io.observe(flowSection);
}

// ---------- screenshot tabs ----------
const tabs = [...document.querySelectorAll('.shots-tabs [role="tab"]')];
const shotImg = document.getElementById('shot-img');
const shotCap = document.getElementById('shot-cap');
const shotPanel = document.getElementById('shot-panel');

function showShot(key, focus) {
  const s = SHOTS[key];
  if (!s) return;
  shotImg.src = s.src;
  shotImg.alt = s.alt;
  shotCap.innerHTML = s.cap;
  tabs.forEach((t) => {
    const on = t.dataset.shot === key;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    if (on && focus) t.focus();
  });
  shotPanel.setAttribute('aria-labelledby', document.querySelector(`[data-shot="${key}"]`).id);
}

tabs.forEach((t, i) => {
  t.addEventListener('click', () => showShot(t.dataset.shot));
  t.addEventListener('keydown', (e) => {
    let j = null;
    if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
    if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
    if (e.key === 'Home') j = 0;
    if (e.key === 'End') j = tabs.length - 1;
    if (j !== null) { e.preventDefault(); showShot(tabs[j].dataset.shot, true); }
  });
});
