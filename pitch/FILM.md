# OpenArms launch film: plan, scripts and shot list

HackPrinceton Fall 2026 · drafted November 15, 05:15 ET · owner Victor · edit source in [`pitch/film/`](film/) (HyperFrames) · latest cut [`pitch/renders/animatic-v3.mp4`](renders/animatic-v3.mp4)

> **Update 05:40 · format changed (Victor).** One opening skit, then each speaker takes over the centre of the frame for their first line and shrinks into a talking-head circle in the bottom-right corner for the rest of their section. No mid-film skits. Order: Victor (problem, student flow, agent) → Duc (skills and learning in simulation) → Joseph (simulation) → Stefanie (hardware) → close. The real arm footage (`v1`–`v4`) is in; the pour runs at 2× and the app at 1.6× so they keep pace. **The current lines and recording instructions are in [SCRIPTS.md](SCRIPTS.md); they replace the timeline below where they differ.** Latest cut: [`renders/animatic-v3.mp4`](renders/animatic-v3.mp4).

**One film, 2:00, 1920×1080 at 30 fps.** It works as the Devpost video, the table opener and the thing judges remember. It is an ad first and a pitch second: the OpenNote *Introducing Feynman-3* structure (logo, the product doing the thing, end card), with our four voices carrying the argument.

## What we are selling

**You're the scientist. Ollie's the hands.**

Four proof points, in this order, each owned by one speaker:

| # | Claim | Proof on screen | Speaker |
| --- | --- | --- | --- |
| 1 | Students who can't hold a beaker lose control of their own lab, not just the pouring. | Two sourced statistics, then a student directing a real pour. | Victor |
| 2 | Ollie is an agent, not a script: it listens, looks, plans from tested actions, says its plan and waits for yes. | The real student app plus the real arm, side by side. | Victor |
| 3 | Ollie remembers. A task it has done becomes a saved skill: the repeat is one tool call. | The app's own plan card: "New plan · 1 AI expert call" then "Saved skill · 0 AI expert calls". | Duc |
| 4 | It is real hardware we built around, and the simulator matches it. | Arm macro shots, base plate, overhead camera, leader-arm teaching, real pour next to sim pour. | Stef |
| 5 | It scales past the robot. Every lab also runs in simulation of the same arm. | Volcano, Magic Potions, Lava Lamp, Snow renders, labelled Simulation. | Joseph |

**Hand time.** Real-arm footage is on screen for about 55 of the 120 seconds: the cold open, the hero pour, the whole hardware section and the closing wave. Simulation gets about 12 seconds. The arm is the hero; the sims are the "and it scales" beat.

**Look.** The Ollie brand from `victor/user-flow-ui` (`ui/student/DESIGN.md`): cream `#fff6e3`, ink `#1a1538`, tea indigo `#3b34c4`, acid pink `#ff4f9a` for "now/yes", red only for Stop. Bagel Fat One for titles, Atkinson Hyperlegible Next for everything else. Flat colour, capsule shapes, springy motion. The SVG Ollie (`ollieSVG` in `ui/student/app.js`) is the mascot in title cards and does the same poses as the real arm. Footage sits in rounded capsule frames on brand-colour fields, like the Feynman ad's floating windows on off-white. Lab coats and goggles on every person in every shot.

## Timeline and script

About 245 spoken words. Read at a calm pace, about 2.3 words per second. Times are targets; I cut to the recorded reads.

### 0:00–0:07 · Cold open (music only)

- Real bench, white backdrop, arm folded down (Ollie `stop` pose). It rises, opens the gripper "ears", tilts its head. (Shot H1.)
- Smash cut to cream. SVG Ollie does the same wave. Wordmark: **ollie** by OpenArms.

### 0:07–0:27 · The problem · Victor (on camera, lab coat, at the bench)

> Imagine you're a student who knows exactly what you want to test, but you can't hold the beaker. One in five undergrads reports a disability. And when students with physical disabilities were surveyed, about half said they'd been given passive roles in the lab. A partner can do the pouring. But when someone else has the hands, they usually end up making the calls too.

On screen: Victor medium shot, cut to stat cards (big Bagel numerals): **1 in 5** "undergraduates report a disability" (NCES, 2019–20) · **50%** "of students with physical disabilities surveyed were given passive roles in the lab" (Jeannis et al., 2019, 107 students). End on the tagline card: **You're the scientist. Ollie's the hands.**

### 0:27–1:00 · The product · Victor (voice over the hero take)

> So we built Ollie. You just talk to it. Ollie looks at the bench through its camera, works out a plan from moves we've tested on the arm, and tells you that plan before anything happens. Nothing moves until you say yes, and Stop always wins. When it's done, the camera checks what actually happened, and you decide what to test next.

On screen, one continuous real take cut in three places:
1. Student (seen from behind, laptop open to Ollie) says: "Ollie, pour beaker A into flask C." App: "Let me look at the bench and work out a plan."
2. App plan card fills the frame (zoom on "Here's my plan. I won't move until you say yes."), then a pink **Yes, do it** press.
3. Real arm: grasp, lift, pour (side macro, shot H4), return, HOME. Small app window in the corner shows "Ollie is pouring" with the red Stop.
4. App: "Done! I'm back home. What did you notice?" then the prediction / observation / "Why did that happen?" cards, one beat each.

### 1:00–1:20 · Skills · Duc

> The first time Ollie does something new, the AI thinks it through step by step. If it works and passes our checks, Ollie saves it as a skill. Ask again, in your own words, and it's a single tool call: no rethinking, no waiting. In our bench test, planning dropped from fifty-nine seconds to under half a second.

On screen: two plan cards side by side, recorded from the real app: left **"New plan · planned in 3.9 s · 1 AI expert call"**, right **"Saved skill · planned in 0.5 s · 0 AI expert calls"** with Ollie's bubble "I remember this one!". Then a counter card: **58.8 s → 0.41 s** "request to exact plan, same task, new wording" (Duc's demo-bench run). Duc on camera for the first line if possible.

### 1:20–1:40 · Hardware · Stef

> Ollie is an open-source SO-101 arm, about a hundred and twenty dollars in parts. We printed a base plate with markers so the beakers land in the same place every time, mounted a camera overhead, and taught the arm a real pour by hand. Then we lined our simulator up with that recording, so what Ollie rehearses on screen is what the real arm does.

On screen: macro slider across servos (H6); base plate with ArUco markers and rulers (H7); overhead camera view with the centimetre grid (H8, `firmware/openarms_camera` output); Stef teaching with the leader arm while the follower copies (H5); split screen: real pour vs MuJoCo pour of the same take.

### 1:40–1:52 · Scale · Joseph

> Not every school can buy a robot. So every experiment also runs in a physics simulation of the same arm: volcanoes, potions, lava lamps, straight from a twenty-dollar science kit. Same conversation, same checks.

On screen: four-up grid then quick cuts of the clean renders (no burned-in text): volcano foam, potions pink-to-purple, lava lamp, snow. Small brand label **Simulation** on each. End on the student app's experiment shelf.

### 1:52–2:00 · Close (Victor, then music)

> OpenArms. It personalizes to the student and scales to the school.

On screen: team in lab coats behind the bench; the real arm waves. End card on tea indigo: **ollie** by OpenArms · "You're the scientist. Ollie's the hands." · github.com/VictorJimenez3/OpenArms.

## Ollie, the mascot, in the film

Ollie is the same SVG character as the student app, with the app's own poses (`idle`, `hello`, `listen`, `think`, `pour`, `wave`, `stop`) ported from `ui/student/style.css` to the film timeline. Rule: **Ollie mirrors the real arm.** When the arm moves, Ollie strikes the same pose; Ollie never stands in for footage of a result.

| Time | Ollie | Why |
| --- | --- | --- |
| 0:00–0:03.5 | Split screen: real arm rises on the left, Ollie goes `stop` → `hello` → `wave` on the right in sync | Tells the viewer in three seconds that Ollie *is* the arm |
| 0:03.5–0:07 | Wordmark, wave, blink | Brand moment |
| 0:11–0:22 | Peeks up from the bottom corner of each stat card: `listen`, then `think`, then folds to `stop` on the 50% card | Keeps the stats warm instead of grim |
| 0:22–0:27 | Pops up beside the tagline and waves | "Ollie's the hands" lands on Ollie |
| 0:40–0:52 | Corner companion circle (the "tutor in the corner" idea) pours while the real arm pours; bubble: "Ok, I'm pouring. Say stop any time." (Ollie's real app line) | Links the app character to the physical motion |
| 1:12–1:20 | Peeks beside the 58.8 s → 0.41 s counter: `think`, then `wave` and nods | "I remember this one!" energy |
| 1:20–1:52 | Companion watches the hardware and pours along with each simulation | Same character across real and simulated |
| 1:55–2:00 | End card: `stop` → `hello` → `wave` | Bookends the cold open |

Ollie does not appear on top of the app footage, because the app already shows Ollie there. If the arm can do a short "hello" (rise, open gripper, tilt) under an operator, film it as H1 so the opening twin shot is real.

## Honesty rules for the edit

- Every simulated frame carries a small **Simulation** label. Real footage carries nothing, or **Real arm** if a split screen could confuse.
- The hero take is captioned for what it is. If the app drives the real arm (bench lane), say "live". If the arm replays the pour Stef recorded while the app runs the same plan in simulation, the corner label reads **Real arm · recorded pour** and the app window reads **Ollie app · live simulation**. Do not cut them so it looks like one live system if it was not.
- The skill numbers on screen are the app's own readouts and Duc's logged run. They are simulator timings.
- No measured-learning, safety-certified or "works for every disability" claims. "Tested with students" is not true yet; we say what we built.

## Shot list for the bench (Stef and Duc drive the arm, Victor films)

Shoot on an iPhone, 4K 30 fps, landscape, 1× lens, exposure and focus locked (long-press), no cinematic mode. White poster board behind and under the bench. Clean the bench of cables and cups that are not A and C. Three takes of each. An operator stays at the arm with a hand near Stop for every motion.

| ID | Shot | Length | Notes |
| --- | --- | --- | --- |
| H1 | Arm rises from folded, opens gripper, small head tilt | 6 s | Teleop or a recorded pose sequence. Static tripod, low angle. This is the opening frame. |
| H2 | Wide hero: student from behind at laptop, arm and vessels in frame | 30 s | The whole A→C pour, return, HOME in one take. Laptop shows the Ollie app. |
| H3 | Top-down pour | 25 s | Phone on the overhead mount or held flat above. Same run as H2 if two phones. |
| H4 | Side macro on the liquid leaving A into C | 8 s | 2× lens is fine here. Coloured water (food colour) reads best. |
| H5 | Leader arm teaching, follower copying | 10 s | Stef's hands on the leader, both arms in frame. |
| H6 | Slow slide across servos and joints | 6 s | Move the phone slowly along a ruler for a slider look. |
| H7 | Base plate, markers and rulers, empty then with vessels set down | 6 s | Overhead, then a 45° angle. |
| H8 | Screen recording of the overhead camera view with the grid | 6 s | From the bench tools. |
| H9 | Stop: arm moving, someone says "Stop", arm halts | 6 s | Shows control. Only if it is safe and works on the real path. |
| H10 | Team in lab coats and goggles behind the bench, arm waves | 5 s | Closing shot. |
| T1–T4 | Each speaker's first line on camera, medium shot | 5 s each | Same backdrop, lab coat, eye line just off the lens. |

## Voiceover

Each speaker records their lines as one voice memo on an iPhone, 15 cm from the mouth, in a closet, car or under a coat. Three full takes, a two-second pause between takes. Send as `vo-<name>.m4a`. I cut the best take with a whisper transcript and match captions to the words.

## Music

One licensed track, warm and upbeat, around 100 BPM, piano or plucked synth, no vocals (YouTube Audio Library or Pixabay Music; keep the licence page link). Name it `music.mp3` and note the source in `audio/CREDITS.txt`.

## How the edit is built

- **Engine:** HyperFrames (HTML/GSAP rendered frame by frame to MP4). Source: `pitch/film/` (`build.py` writes `index.html`). Raw bench footage and voice files stay in Victor's local `~/OpenArms/openarms-film/` drop folder so they don't bloat Git; only the final cut gets committed.
- **Brand:** fonts and tokens copied from `ui/student`; the SVG Ollie is reused as the mascot.
- **App footage:** recorded from the real student app with `pitch/scripts/capture_app_run.sh` (Playwright, 1920×1080). It runs one lab end to end: predict, direct, plan, yes, pour, observe, then "Do it again" so the saved-skill card is on camera.
- **Simulation footage:** `pitch/scripts/clean_smartivity.py` re-renders Joseph's recorded Smartivity episodes from their saved simulator states without the burned-in captions, so the film adds one small brand label instead. Volcano, Potions and Lava Lamp are done.
- **Captions:** word-timed from the voiceover with `mlx_whisper`.
- **Check:** `npx hyperframes check` plus frame snapshots at every cut; one human watches the final render with sound before upload.

## Drop folder

Put files here and tell Devin:

```
~/OpenArms/openarms-film/footage/hand/   H1..H10, T1..T4  (keep the original names, add the shot ID: H4-take2.mov)
~/OpenArms/openarms-film/footage/team/   anything else worth using
~/OpenArms/openarms-film/audio/          vo-victor.m4a, vo-duc.m4a, vo-stef.m4a, vo-joseph.m4a, music.mp3
```

Any AI-generated clips go in `footage/ai/` with the tool's name in the file name. They are b-roll only; never for the arm, the app or a result.
