"""Generates index.html (the first-cut animatic). Edit the SHOTS/CAPTIONS tables, rerun, then `npm run check`."""
import json
W = []
def clip(id, start, dur, inner='', cls='', style='', z=1, extra=''):
    W.append(f'<div id="{id}" class="clip {cls}" data-start="{start}" data-duration="{dur}" style="z-index:{z};{style}" {extra}>{inner}</div>')
VIDS = []
def video(id, src, start, dur, mstart=0, cls='', style='', box='', z=5):
    VIDS.append(f'<video id="{id}" class="clip {cls}" src="assets/media/{src}" data-start="{start}" data-duration="{dur}" data-media-start="{mstart}" muted playsinline style="z-index:{z};{box}{style}"></video>')
    return ''
def placeholder(shot, desc):
    return f'<div class="ph"><span class="ph-id">{shot}</span><span class="ph-desc">{desc}</span><span class="ph-note">real footage goes here</span></div>'

OLLIE = '''<svg class="ollie" viewBox="-50 -20 300 250"><ellipse class="o-floor" cx="100" cy="220" rx="76" ry="8"/><rect class="o-body" x="44" y="188" width="112" height="32" rx="16"/><g class="o-shoulder"><rect class="o-body" x="82" y="112" width="36" height="92" rx="18"/><g class="o-elbow"><rect class="o-body" x="84" y="50" width="32" height="86" rx="16"/><g class="o-head"><rect class="o-body o-ear-l" x="74" y="-10" width="14" height="38" rx="7"/><rect class="o-body o-ear-r" x="112" y="-10" width="14" height="38" rx="7"/><rect class="o-body" x="58" y="12" width="84" height="62" rx="27"/><g class="o-eyes"><circle cx="83" cy="42" r="8"/><circle cx="117" cy="42" r="8"/></g></g><circle class="o-joint" cx="100" cy="66" r="9"/></g><circle class="o-joint" cx="100" cy="124" r="11"/></g><circle class="o-joint" cx="100" cy="194" r="12"/></svg>'''

import os
SAFE = os.environ.get('SAFE') == '1'
# Speaker talking-head videos: drop assets/media/talk-<name>.mp4 (landscape selfie, one take of the whole section).
SPEAKERS = {  # name: (section start, section end, takeover seconds, label)
 'victor': (14, 51, 2.5, 'Victor · agent and student flow'),
 'duc': (51, 73, 2.5, 'Duc · skills'),
 'joseph': (73, 92, 2.5, 'Joseph · simulation'),
 'stef': (92, 112, 2.5, 'Stefanie · hardware'),
}
FULL = 'left:150px;top:90px;width:1620px;height:911px;border-radius:44px;object-fit:cover;'
TALL_L = 'left:150px;top:110px;width:506px;height:900px;border-radius:44px;object-fit:cover;'
TALL_C = 'left:690px;top:60px;width:540px;height:960px;border-radius:44px;object-fit:cover;'
WIDE_R = 'left:740px;top:150px;width:1080px;height:608px;border-radius:44px;object-fit:cover;'

def speaker(name):
    st, en, take, label = SPEAKERS[name]
    src = f'talk-{name}.mp4'
    have = os.path.exists(f'assets/media/{src}')
    if have:
        video(f'v-take-{name}', src, st, take, 0, box='left:0;top:0;width:1920px;height:1080px;object-fit:cover;')
        video(f'v-circ-{name}', src, st + take, en - st - take, take, box='right:40px;bottom:34px;width:300px;height:300px;border-radius:50%;object-fit:cover;box-shadow:0 0 0 8px #fff6e3;', z=45)
        W.append(f'<audio id="a-{name}" class="clip" src="assets/media/{src}" data-start="{st}" data-duration="{en-st}"></audio>')
    elif SAFE:
        clip(f's-take-{name}', st, take, f'<div class="stat"><div class="num">{label.split(" · ")[1].capitalize()}</div><div class="lbl">{label.split(" · ")[0]}</div></div>', 'field-tea')
    else:
        clip(f's-take-{name}', st, take, placeholder(name.upper(), f'{label}: on camera, lab coat, centre frame'), 'field-ink')
        clip(f's-circ-{name}', st + take, en - st - take, f'<div class="circ"><span>{name.upper()}</span><small>talking head</small></div>', 'overlay', z=45, extra='data-layout-allow-overlap data-layout-allow-occlusion')
    if SAFE and not have: return
    clip(f's-name-{name}', st + .3, 3.2, f'<div class="name">{label}</div>', 'overlay', z=46, extra='data-layout-allow-overlap data-layout-allow-occlusion')

# 0:00-0:05 the real arm wakes up; Ollie copies it
clip('s-open', 0, 5.1, f'<div class="half right twin" id="o-twin">{OLLIE}</div><div class="chip">Real arm</div>', 'field-ink')
video('v-rise', 'arm-rise.mp4', 0, 5.1, 0, box=TALL_L.replace('150px', '260px'))
# 0:05-0:11 skit (filmed once, before anything else)
clip('s-skit', 5.1, 5.9, '<div class="stat"><div class="num">“Wait, I wanted to—”</div><div class="lbl">When someone else has the hands, they make the calls.</div></div>' if SAFE and not os.path.exists('assets/media/skit.mp4') else placeholder('SKIT', 'Student in a lab coat, hands in lap. Partner grabs the beaker and pours without asking. Student: "Wait, I wanted to—"'), 'field-ink')
# 0:11-0:14 brand
clip('s-logo', 11, 3, f'<div class="logo-wrap"><div class="logo-ollie" id="o-logo">{OLLIE}</div><div class="wordmark"><span class="wm">ollie</span><span class="by">by OpenArms</span></div></div>', 'field-cream')

# VICTOR 0:14-0:51
speaker('victor')
clip('s-stat1', 16.5, 5, f'<div class="stat"><div class="num">1 in 5</div><div class="lbl">US undergraduates report a disability.</div><div class="src">NCES, 2019–20</div></div>', 'field-tea')
clip('s-stat2', 21.5, 5, f'<div class="stat"><div class="num">50%</div><div class="lbl">of students with physical disabilities surveyed had been given passive roles in the lab.</div><div class="src">Jeannis et al., 2019 · 107 students</div></div>', 'field-pink')
clip('s-tag', 26.5, 3, f'<div class="tag"><h1>You’re the scientist.<br>Ollie’s the hands.</h1><div class="tag-ollie" id="o-tag">{OLLIE}</div></div>', 'field-tea')
clip('s-app1', 29.5, 5.5, '<div class="chip">Ollie app · live simulation · 1.6×</div>', 'field-cream')
video('v-app1', 'app-fast.mp4', 29.5, 5.5, 12.5, box=FULL)
clip('s-split', 35, 16, '<div class="chip">Real arm · 2×</div><div class="chip right-chip">Ollie app · live simulation · 1.6×</div>', 'field-tea')
video('v-pour', 'arm-pour-2x.mp4', 35, 16, 1, box=TALL_L)
video('v-app2', 'app-fast.mp4', 35, 16, 19.5, box=WIDE_R)

# DUC 0:51-1:13
speaker('duc')
CHECKS = ['Normal run', 'Beaker missing', 'Beakers swapped', 'Beaker moved', 'Camera blocked', 'Stale picture', 'Consent check', 'Stop check']
ticks = ''.join(f'<li id="tick{i}"><b>✓</b>{c}</li>' for i, c in enumerate(CHECKS))
clip('s-learn', 53.5, 6.5, f'<div class="learn"><h2>Before Ollie saves a skill, it replays it in simulation</h2><ul>{ticks}</ul></div><div class="chip">Simulation</div>', 'field-ink')
video('v-learn', 'sim-volcano.mp4', 53.5, 6.5, 6, box='left:1010px;top:250px;width:780px;height:439px;border-radius:36px;object-fit:cover;')
clip('s-skill', 60, 6.5, '<div class="pair"><div class="card"><div class="card-h">First time</div><div class="frame card-frame"><img src="assets/media/new-plan-crop.png"></div><div class="card-k">New plan · 1 AI expert call</div></div><div class="card"><div class="card-h">Second time</div><div class="frame card-frame"><img src="assets/media/saved-skill-crop.png"></div><div class="card-k pink">Saved skill · 0 AI expert calls</div></div></div>', 'field-cream')
clip('s-count', 66.5, 6.5, f'<div class="stat"><div class="num"><span id="cnt-a">58.8 s</span> <span class="arrow">→</span> <span id="cnt-b">0.41 s</span></div><div class="lbl">request to exact plan, same task, new wording</div><div class="src">6 model calls → 0 · logged MuJoCo bench run</div></div><div class="peek" id="o-peek3">{OLLIE}</div>', 'field-ink')

# JOSEPH 1:13-1:32
speaker('joseph')
GB = {'volcano': 'left:150px;top:110px;width:796px;height:410px;border-radius:32px;object-fit:cover;', 'potions': 'left:974px;top:110px;width:796px;height:410px;border-radius:32px;object-fit:cover;', 'lava': 'left:150px;top:546px;width:796px;height:410px;border-radius:32px;object-fit:cover;'}
clip('s-grid', 75.5, 4.5, f'<div class="grid"><div></div><div></div><div></div><div class="g g-shelf">{OLLIE}<span>3 labs · 1 arm</span></div></div><div class="chip">Simulation</div>', 'field-ink')
for n, m in [('volcano', 9), ('potions', 12), ('lava', 10)]:
    video('vg-' + n, f'sim-{n}.mp4', 75.5, 4.5, m, box=GB[n])
for i, (n, m, name) in enumerate([('volcano', 11, 'Erupting Volcano'), ('potions', 15, 'Magic Potions'), ('lava', 13, 'Lava Lamp')]):
    s = round(80 + i * 4, 2)
    clip(f's-sim-{n}', s, 4, f'<div class="chip">Simulation · {name}</div>', 'field-ink')
    video('v-' + n, f'sim-{n}.mp4', s, 4, m, box=FULL)

# STEF 1:32-1:52
speaker('stef')
clip('s-hw', 94.5, 9.7, '<div class="chip">Real arm</div><div class="hw-copy"><h2>SO-101</h2><p>open source · about $120 in parts · taught by hand</p></div>', 'field-tea')
video('v-dolly', 'arm-dolly.mp4', 94.5, 5.9, 0, box=TALL_L)
video('v-macro', 'arm-macro.mp4', 100.4, 3.8, 0, box=TALL_L)
clip('s-twin', 104.2, 7.8, '<div class="chip">Real arm</div><div class="chip right-chip">Simulation · same arm model</div>', 'field-ink')
video('v-real2', 'arm-pour-2x.mp4', 104.2, 7.8, 5, box=TALL_L)
video('v-sim2', 'sim-volcano.mp4', 104.2, 7.8, 8, box=WIDE_R)

# CLOSE 1:52-2:00
clip('s-team', 112, 3, f'<div class="half right twin">{OLLIE}</div><div class="chip">Real arm</div>', 'field-ink') if SAFE else clip('s-team', 112, 3, placeholder('TEAM', 'All four in lab coats behind the bench; the arm waves'), 'field-ink')
if SAFE: video('v-wave', 'arm-rise.mp4', 112, 3, 2, box=TALL_L.replace('150px', '260px'))
clip('s-end', 115, 5, f'<div class="end"><div class="logo-ollie" id="o-end">{OLLIE}</div><div class="wordmark light"><span class="wm">ollie</span><span class="by">by OpenArms</span></div><p class="end-tag">Personalizes to the student. Scales to the school.</p><p class="end-url">github.com/VictorJimenez3/OpenArms</p></div>', 'field-tea')

CAPTIONS = [
 (5.1, 5.9, '“Wait, I wanted to—”'),
 (14, 2.5, "Imagine you're a student who knows exactly what to test, but can't hold the beaker."),
 (16.5, 5, "One in five undergrads reports a disability."),
 (21.5, 5, "In one national survey, half of students with physical disabilities were given passive roles in the lab."),
 (26.5, 3, "Someone else had the hands, so someone else made the calls. So we built Ollie."),
 (29.5, 5.5, "You just talk. Ollie looks at the bench and plans from moves we've tested on the arm."),
 (35, 6, "It tells you the plan, and nothing moves until you say yes."),
 (41, 10, "Then a camera checks what actually happened, and you decide what to test next."),
 (51, 2.5, "The first time Ollie does something new, the AI reasons it out step by step."),
 (53.5, 6.5, "Before it's saved, we replay it in simulation: missing, swapped and moved beakers, a blocked camera, and Stop."),
 (60, 6.5, "Only then does it become a skill. Next time, in any words, it's one tool call."),
 (66.5, 6.5, "Fifty-nine seconds down to under half a second."),
 (73, 2.5, "Not every school can afford a robot."),
 (75.5, 8.5, "So every lab also runs in a physics simulation of the same arm, straight from a twenty-dollar science kit."),
 (84, 8, "Volcanoes, potions, lava lamps. Same conversation, same checks, no hardware."),
 (92, 2.5, "Ollie is an open-source SO-101 arm, about a hundred and twenty dollars in parts."),
 (94.5, 9.7, "We taught it a real pour by hand, and gave it rulers and an overhead camera so it knows where every beaker is."),
 (104.2, 7.8, "Then we lined our simulator up with that recording, so what Ollie rehearses is what the real arm does."),
 (112, 8, "OpenArms. It personalizes to the student and scales to the school."),
]
for i, (s, d, t) in enumerate(CAPTIONS):
    W.append(f'<div id="cap-{i}" class="clip cap" data-start="{s}" data-duration="{d}" data-track-kind="captions" style="z-index:50"><span>{t}</span></div>')

ANIM = '''
const tl = gsap.timeline({ paused: true });
const pop = (sel, at) => tl.fromTo(sel, { scale: .9, opacity: 0 }, { scale: 1, opacity: 1, duration: .5, ease: "back.out(1.6)" }, at);
const POSE = { idle:[8,-22,16,0], hello:[-12,30,-34,6], listen:[20,34,-30,5], think:[-14,-28,58,0], pour:[22,48,52,-3], wave:[0,0,0,6], stop:[-34,104,-70,0] };
const rig = (id, cues) => {
  const el = document.getElementById(id); if (!el) return;
  const q = (c) => el.querySelector(c), st = { s:0, e:0, h:0, ear:0, b:1 };
  const apply = () => {
    q('.o-shoulder').setAttribute('transform', `rotate(${st.s} 100 194)`);
    q('.o-elbow').setAttribute('transform', `rotate(${st.e} 100 124)`);
    q('.o-head').setAttribute('transform', `rotate(${st.h} 100 66)`);
    q('.o-ear-l').setAttribute('transform', `translate(${-st.ear} 0)`);
    q('.o-ear-r').setAttribute('transform', `translate(${st.ear} 0)`);
    q('.o-eyes').setAttribute('transform', `translate(0 42) scale(1 ${st.b}) translate(0 -42)`);
  };
  const [s0, e0, h0, r0] = POSE[cues[0][1]]; Object.assign(st, { s:s0, e:e0, h:h0, ear:r0 }); apply();
  tl.to(st, { s:s0, duration: .01, onUpdate: apply }, 0);
  for (const [t, pose] of cues) {
    if (pose === 'blink') { tl.to(st, { b:.1, duration:.08, yoyo:true, repeat:1, onUpdate: apply }, t); continue; }
    if (pose === 'nod') { tl.to(st, { h:'+=10', duration:.35, yoyo:true, repeat:3, ease:'sine.inOut', onUpdate: apply }, t); continue; }
    const [ps, pe, ph, pr] = POSE[pose];
    tl.to(st, { s:ps, e:pe, h:ph, ear:pr, b: pose === 'stop' ? .14 : 1, duration:.8, ease:'back.out(1.7)', onUpdate: apply }, t);
    if (pose === 'wave') tl.to(st, { keyframes: [{ h:-16, duration:.4 }, { h:14, duration:.55 }, { h:0, duration:.4 }], ease:'sine.inOut', onUpdate: apply }, t + .5);
  }
};
const wave = (root, at) => tl.fromTo(`${root} .ollie`, { y: 40, scale: .92 }, { y: 0, scale: 1, duration: .7, ease: "back.out(2.2)" }, at);
wave("#s-logo", 3.6);
rig("o-twin", [[0,"stop"],[1.2,"hello"],[3,"wave"]]);
rig("o-logo", [[11,"hello"],[11.8,"wave"],[13.4,"blink"]]);
rig("o-tag", [[26.5,"stop"],[26.9,"hello"],[27.8,"wave"]]);
rig("o-peek3", [[66.5,"think"],[67.8,"wave"],[70,"nod"]]);
rig("o-end", [[115,"stop"],[115.6,"hello"],[116.6,"wave"],[119,"blink"]]);
{ const c = document.querySelector("#s-count .peek"); tl.fromTo(c, { y: 260 }, { y: 0, duration: .7, ease: "back.out(1.6)" }, 67.1); }
document.querySelectorAll(".learn li").forEach((li, i) => tl.fromTo(li, { opacity: .25, x: -16 }, { opacity: 1, x: 0, duration: .25, ease: "power2.out" }, 54 + i * .7));
document.querySelectorAll(".circ").forEach((el) => tl.fromTo(el, { scale: 2.2, opacity: 0 }, { scale: 1, opacity: 1, duration: .5, ease: "power3.out" }, +el.closest(".clip").dataset.start));
document.querySelectorAll(".name").forEach((el) => tl.fromTo(el, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: .35, ease: "power2.out" }, +el.closest(".clip").dataset.start)); pop("#s-logo .wordmark", 4.0);
pop("#s-stat1 .num", 16.6); pop("#s-stat2 .num", 21.6);
tl.fromTo("#s-tag h1", { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: .5, ease: "power3.out" }, 26.55); wave("#s-tag", 26.7);
pop("#s-skill .card", 60.05);
tl.fromTo("#cnt-b", { opacity: 0, x: -20 }, { opacity: 1, x: 0, duration: .5, ease: "power3.out" }, 67.4);
pop("#s-grid .g-shelf", 75.55);
document.querySelectorAll(".stat, .ph").forEach((el) => { const c = el.closest(".clip"); tl.fromTo(el, { scale: 1 }, { scale: 1.035, duration: +c.dataset.duration, ease: "none" }, +c.dataset.start); }); wave("#s-end", 115.2); pop("#s-end .end-tag", 116);
document.querySelectorAll(".cap span").forEach((el) => {
  const c = el.parentElement; tl.fromTo(el, { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: .25, ease: "power2.out" }, +c.dataset.start + .02);
});
window.__timelines = window.__timelines || {}; window.__timelines["main"] = tl; tl.seek(0);
'''
CSS = open('film.css').read()
html = f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=1920, height=1080">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>{CSS}</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="120" data-width="1920" data-height="1080">
{chr(10).join(W)}
{chr(10).join(VIDS)}
</div>
<script>{ANIM}</script></body></html>'''
open('index.html', 'w').write(html)
print('ok', len(W))
