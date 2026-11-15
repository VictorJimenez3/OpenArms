"""Generates index.html (the first-cut animatic). Edit the SHOTS/CAPTIONS tables, rerun, then `npm run check`."""
import json
W = []
def clip(id, start, dur, inner='', cls='', style='', z=1, extra=''):
    W.append(f'<div id="{id}" class="clip {cls}" data-start="{start}" data-duration="{dur}" style="z-index:{z};{style}" {extra}>{inner}</div>')
VIDS = []
def video(id, src, start, dur, mstart=0, cls='', style='', box=''):
    VIDS.append(f'<video id="{id}" class="clip {cls}" src="assets/media/{src}" data-start="{start}" data-duration="{dur}" data-media-start="{mstart}" muted playsinline style="z-index:5;{box}{style}"></video>')
    return ''
def placeholder(shot, desc):
    return f'<div class="ph"><span class="ph-id">{shot}</span><span class="ph-desc">{desc}</span><span class="ph-note">real footage goes here</span></div>'

OLLIE = '''<svg class="ollie" viewBox="-50 -20 300 250"><ellipse class="o-floor" cx="100" cy="220" rx="76" ry="8"/><rect class="o-body" x="44" y="188" width="112" height="32" rx="16"/><g class="o-shoulder"><rect class="o-body" x="82" y="112" width="36" height="92" rx="18"/><g class="o-elbow"><rect class="o-body" x="84" y="50" width="32" height="86" rx="16"/><g class="o-head"><rect class="o-body o-ear-l" x="74" y="-10" width="14" height="38" rx="7"/><rect class="o-body o-ear-r" x="112" y="-10" width="14" height="38" rx="7"/><rect class="o-body" x="58" y="12" width="84" height="62" rx="27"/><g class="o-eyes"><circle cx="83" cy="42" r="8"/><circle cx="117" cy="42" r="8"/></g></g><circle class="o-joint" cx="100" cy="66" r="9"/></g><circle class="o-joint" cx="100" cy="124" r="11"/></g><circle class="o-joint" cx="100" cy="194" r="12"/></svg>'''

# 0:00-0:07 cold open
clip('s-open', 0, 3.5, f'<div class="half left">{placeholder("H1", "Real arm rises from folded, opens its gripper ears")}</div><div class="half right twin" id="o-twin">{OLLIE}</div>', 'field-ink')
clip('s-logo', 3.5, 3.5, f'<div class="logo-wrap"><div class="logo-ollie" id="o-logo">{OLLIE}</div><div class="wordmark"><span class="wm">ollie</span><span class="by">by OpenArms</span></div></div>', 'field-cream')
# 0:07-0:27 problem
clip('s-victor', 7, 4, placeholder('T1', 'Victor, lab coat, at the bench: "Imagine you\'re a student…"'), 'field-ink')
clip('s-stat1', 11, 5.5, f'<div class="stat"><div class="num">1 in 5</div><div class="lbl">US undergraduates report a disability.</div><div class="src">NCES, 2019–20</div></div><div class="peek" id="o-peek1">{OLLIE}</div>', 'field-tea')
clip('s-stat2', 16.5, 5.5, f'<div class="stat"><div class="num">50%</div><div class="lbl">of students with physical disabilities surveyed had been given passive roles in the lab.</div><div class="src">Jeannis et al., 2019 · 107 students</div></div><div class="peek" id="o-peek2">{OLLIE}</div>', 'field-pink')
clip('s-tag', 22, 5, f'<div class="tag"><h1>You’re the scientist.<br>Ollie’s the hands.</h1><div class="tag-ollie" id="o-tag">{OLLIE}</div></div>', 'field-tea')
# 0:27-1:00 product
clip('s-app1', 27, 13, f'<div class="frame big">{video("v-app1","app-run-cold.mp4",27,13,8, box="left:150px;top:90px;width:1620px;height:911px;border-radius:44px;object-fit:cover;")}</div><div class="chip">Ollie app · live simulation</div>', 'field-cream')
clip('s-split', 40, 12, f'<div class="frame half left">{video("v-app2","app-run-cold.mp4",40,12,32, box="left:80px;top:150px;width:860px;height:760px;border-radius:44px;object-fit:cover;object-position:30% 50%;")}</div><div class="half right">{placeholder("H2/H4","Real arm: grasp, lift, pour A→C, return, HOME (side macro on the liquid)")}</div><div class="chip">Ollie app · live simulation</div><div class="chip right-chip">Real arm</div>', 'field-tea')
clip('s-app3', 52, 8, f'<div class="frame big">{video("v-app3","app-run-cold.mp4",52,8,46, box="left:150px;top:90px;width:1620px;height:911px;border-radius:44px;object-fit:cover;")}</div><div class="chip">Ollie app · live simulation</div>', 'field-cream')
# 1:00-1:20 skills
clip('s-duc', 60, 3, placeholder('T2', 'Duc on camera: "The first time Ollie does something new…"'), 'field-ink')
clip('s-skill', 63, 9, f'<div class="pair"><div class="card"><div class="card-h">First time</div><div class="frame card-frame"><img src="assets/media/new-plan-crop.png"></div><div class="card-k">New plan · 1 AI expert call</div></div><div class="card"><div class="card-h">Second time</div><div class="frame card-frame"><img src="assets/media/saved-skill-crop.png"></div><div class="card-k pink">Saved skill · 0 AI expert calls</div></div></div>', 'field-cream')
clip('s-count', 72, 8, f'<div class="stat"><div class="num"><span id="cnt-a">58.8 s</span> <span class="arrow">→</span> <span id="cnt-b">0.41 s</span></div><div class="lbl">request to exact plan, same task, new wording</div><div class="src">6 model calls → 0 · logged MuJoCo bench run</div></div><div class="peek" id="o-peek3">{OLLIE}</div>', 'field-ink')
# 1:20-1:40 hardware
clip('s-hw1', 80, 5, placeholder('H6', 'Slow slide across the SO-101 servos and joints'), 'field-ink')
clip('s-hw2', 85, 5, placeholder('H7/H8', 'Base plate with ArUco markers and rulers · overhead camera grid'), 'field-ink')
clip('s-hw3', 90, 5, placeholder('H5', 'Stef teaching a pour on the leader arm, follower copies'), 'field-ink')
clip('s-hw4', 95, 5, f'<div class="half left">{placeholder("REAL","Recorded real pour (Stef)")}</div><div class="half right">{placeholder("SIM","Same pour in MuJoCo")}</div><div class="chip">Real arm</div><div class="chip right-chip">Simulation</div>', 'field-tea')
# 1:40-1:52 sims
GB={'volcano':'left:150px;top:110px;width:796px;height:410px;border-radius:32px;object-fit:cover;','potions':'left:974px;top:110px;width:796px;height:410px;border-radius:32px;object-fit:cover;','lava':'left:150px;top:546px;width:796px;height:410px;border-radius:32px;object-fit:cover;'}
grid = ''.join(f'<div class="g">{video("vg-"+n, f"sim-{n}.mp4", 100, 4, m, box=GB[n])}</div>' for n, m in [('volcano', 9), ('potions', 12), ('lava', 10)]) + f'<div class="g g-shelf">{OLLIE}<span>4 labs · 1 arm</span></div>'
clip('s-grid', 100, 4, f'<div class="grid">{grid}</div><div class="chip">Simulation</div>', 'field-ink')
for i, (n, m, name) in enumerate([('volcano', 12, 'Erupting Volcano'), ('potions', 16, 'Magic Potions'), ('lava', 14, 'Lava Lamp')]):
    s = round(104 + i * 2.67, 2)
    clip(f's-sim-{n}', s, 2.67, f'<div class="frame big">{video("v-"+n, f"sim-{n}.mp4", s, 2.67, m, box="left:150px;top:90px;width:1620px;height:911px;border-radius:44px;object-fit:cover;")}</div><div class="chip">Simulation · {name}</div>', 'field-ink')
# 1:52-2:00 close
clip('s-team', 112, 3, placeholder('H10', 'Team in lab coats and goggles behind the bench; the arm waves'), 'field-ink')
clip('s-end', 115, 5, f'<div class="end"><div class="logo-ollie" id="o-end">{OLLIE}</div><div class="wordmark light"><span class="wm">ollie</span><span class="by">by OpenArms</span></div><p class="end-tag">Personalizes to the student. Scales to the school.</p><p class="end-url">github.com/VictorJimenez3/OpenArms</p></div>', 'field-tea')


COMPANION = [(40, 12, 'Ok, I’m pouring. Say stop any time.'), (80, 20, ''), (100, 12, '')]
for i, (st, du, line) in enumerate(COMPANION):
    bubble = f'<div class="bubble">{line}</div>' if line else ''
    clip(f's-buddy{i}', st, du, f'<div class="buddy" id="o-buddy{i}">{OLLIE}</div>{bubble}', 'overlay', z=40, extra='data-layout-allow-overlap data-layout-allow-occlusion')

CAPTIONS = [
 (7, 4, "Imagine you're a student who knows exactly what you want to test, but you can't hold the beaker."),
 (11, 5.5, "One in five undergrads reports a disability."),
 (16.5, 5.5, "And about half of students with physical disabilities were given passive roles in the lab."),
 (22, 5, "When someone else has the hands, they usually end up making the calls too."),
 (27, 6.5, "So we built Ollie. You just talk to it."),
 (33.5, 6.5, "Ollie looks at the bench, works out a plan from moves we've tested on the arm,"),
 (40, 6, "and tells you that plan before anything happens. Nothing moves until you say yes,"),
 (46, 6, "and Stop always wins."),
 (52, 8, "When it's done, the camera checks what actually happened, and you decide what to test next."),
 (60, 6, "The first time Ollie does something new, the AI thinks it through step by step."),
 (66, 6, "If it works and passes our checks, Ollie saves it as a skill. Ask again: one tool call."),
 (72, 8, "In our bench test, planning dropped from fifty-nine seconds to under half a second."),
 (80, 6.5, "Ollie is an open-source SO-101 arm, about a hundred and twenty dollars in parts."),
 (86.5, 6.5, "We printed a base plate with markers, mounted a camera overhead, and taught it a real pour by hand."),
 (93, 7, "Then we lined our simulator up with that recording, so what Ollie rehearses is what the arm does."),
 (100, 6, "Not every school can buy a robot. So every experiment also runs in a simulation of the same arm,"),
 (106, 6, "volcanoes, potions, lava lamps, straight from a twenty-dollar kit. Same conversation, same checks."),
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
rig("o-twin", [[0,"stop"],[.9,"hello"],[2.2,"wave"]]);
rig("o-logo", [[3.5,"hello"],[4.4,"wave"],[6.3,"blink"]]);
rig("o-peek1", [[11,"listen"],[13,"blink"],[14.5,"think"]]);
rig("o-peek2", [[16.5,"think"],[18.5,"stop"]]);
rig("o-tag", [[22,"stop"],[22.6,"hello"],[24,"wave"]]);
rig("o-peek3", [[72,"think"],[73.3,"wave"],[76,"nod"]]);
rig("o-buddy0", [[40,"listen"],[41.5,"pour"],[47,"pour"],[49.5,"wave"]]);
rig("o-buddy1", [[80,"listen"],[83,"blink"],[85,"think"],[90,"listen"],[93,"pour"],[96,"nod"]]);
rig("o-buddy2", [[100,"hello"],[101,"pour"],[104,"think"],[106.7,"pour"],[109.4,"wave"]]);
rig("o-end", [[115,"stop"],[115.6,"hello"],[116.6,"wave"],[119,"blink"]]);
for (const id of ["#s-stat1 .peek","#s-stat2 .peek","#s-count .peek"]) { const c = document.querySelector(id).closest(".clip"); tl.fromTo(id, { y: 260 }, { y: 0, duration: .7, ease: "back.out(1.6)" }, +c.dataset.start + .6); }
document.querySelectorAll(".overlay").forEach((c) => { tl.fromTo(c.querySelector(".buddy"), { scale: 0 }, { scale: 1, duration: .5, ease: "back.out(2)" }, +c.dataset.start + .05); const b = c.querySelector(".bubble"); if (b) tl.fromTo(b, { scale: .6, opacity: 0 }, { scale: 1, opacity: 1, duration: .4, ease: "back.out(2)" }, +c.dataset.start + 1.4); }); pop("#s-logo .wordmark", 4.0);
pop("#s-stat1 .num", 11.1); pop("#s-stat2 .num", 16.6);
tl.fromTo("#s-tag h1", { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: .6, ease: "power3.out" }, 22.1); wave("#s-tag", 22.4);
pop("#s-skill .card", 63.05);
tl.fromTo("#cnt-b", { opacity: 0, x: -20 }, { opacity: 1, x: 0, duration: .5, ease: "power3.out" }, 73.2);
pop("#s-grid .g-shelf", 100.05);
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
