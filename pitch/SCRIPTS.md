# Recording scripts

> **Easiest way to record: follow [RECORD.md](RECORD.md).** Each speaker has a read-along video with these lines as subtitles and a pink dot that sets the pace. The opening skit is dropped; the film opens on the real arm and a "Meet Ollie" card.

Four speakers, one take each, plus one opening skit. Read these straight to camera. The edit already exists (`pitch/renders/submit-safe-v5.mp4`); your video drops into it.

## How the film uses you

1. **Opening skit** (filmed once, 6 seconds). The only acted scene.
2. **Your section starts with you taking over the whole frame**, centred, for your first line (about 2.5 seconds).
3. **Then you shrink into a circle in the bottom-right corner** and keep talking while the product, arm and simulation play. You stay in the circle until the next person takes over.

No skits or cutaways in the middle. Lab coat on, goggles optional.

## How to record your take

- **Phone landscape**, at eye level, about an arm's length away. Head and shoulders, **centred** in the frame (the circle crops the middle).
- Plain wall behind you, light in front of you, quiet room. Look into the lens, not the screen.
- Read your **whole section in one take**: first line, a one-beat pause, then the rest. Do three takes. If you stumble, pause two seconds and restart the sentence; we cut it.
- Calm and a little slower than feels natural. The times below are the target; within 2 seconds is fine.
- Name the file `talk-<name>.mp4` (`talk-victor`, `talk-duc`, `talk-joseph`, `talk-stef`) and AirDrop it to Victor.

## Skit · 0:05–0:11 · two people, filmed once

Two lab coats at the bench. The **student** sits with hands resting in their lap and looks at the beaker. The **partner** picks the beaker up and pours it into the bowl without asking.

> **Student** (leaning in, too late): "Wait, I wanted to—"

Hold on the student's face for one second after the line. Shoot landscape from the side so both people and the bench are in frame. Keep it respectful: the student is capable and engaged; the problem is that the partner made the call.

## Victor · 0:14–0:51 · the problem, the student flow, the agent

**Centre (takeover):**
> Imagine you're a student who knows exactly what to test, but can't hold the beaker.

**Circle:**
> One in five undergrads reports a disability. In one survey, half of students with physical disabilities were given passive roles in the lab. Someone else had the hands, so someone else got to be the scientist. We wanted to give that back. So we built Ollie.
>
> You just talk. Ollie looks at the bench and plans from moves we've tested on the arm. It tells you the plan, and nothing moves until you say yes. Then a camera checks what actually happened, and you decide what to test next.

What plays behind you: the two statistic cards, the tagline, the Ollie app planning the pour (1.6× speed), then the real arm pouring (2× speed) next to the app.

## Duc · 0:51–1:13 · skills and how Ollie learns

**Centre (takeover):**
> The first time Ollie does something new, the AI reasons it out step by step.

**Circle:**
> Before it's saved, we replay it in simulation: missing and moved beakers, a blocked camera, and Stop. Only then does it become a skill. Next time, in any words, it's one tool call. Fifty-nine seconds, down to under half a second.

What plays behind you: the checklist of simulated checks, the "New plan · 1 AI expert call" card next to "Saved skill · 0 AI expert calls", then 58.8 s → 0.41 s.

## Joseph · 1:13–1:32 · simulation

**Centre (takeover):**
> Not every school can afford a robot.

**Circle:**
> So every lab also runs in a physics simulation of the same arm, straight from a twenty-dollar science kit. Volcanoes, potions, lava lamps. Same conversation, same checks, no hardware.

What plays behind you: the three simulated experiments as a grid, then each one full screen, all labelled Simulation.

## Stefanie · 1:32–1:52 · hardware

**Centre (takeover):**
> Ollie is an open-source SO-101 arm, about a hundred and twenty dollars in parts.

**Circle:**
> We taught it a real pour by hand, and gave it rulers and an overhead camera so it knows where every beaker is. Then we lined our simulator up with that recording, so what Ollie rehearses is what the real arm does.

What plays behind you: the slow shot up the arm, the gripper close-up, then the real pour next to the simulated arm.

## Close · 1:52–2:00 · everyone

All four in lab coats behind the bench while the arm waves (Stef or Duc runs it, operator at the arm). Victor says:

> OpenArms. Every student should be welcomed into the lab with open arms.

## Optional: fresher app footage (Victor)

The film already uses a real run of the student app recorded at 5 a.m. To re-record it at full quality with a true first-time plan:

1. Start the lab server on a fresh data folder (runbook in `docs/LAB_RUNBOOK.md`, or `agentic/scripts/run_demo_app.sh devin-sol-fast medium 8031` on `victor/user-flow-ui`).
2. Run `pitch/scripts/capture_app_run.sh http://127.0.0.1:8031 volcano footage/app/volcano-1080.webm "Ollie, could you pour the beaker at A into the flask at C?"`. It clicks through predict → direct → plan → yes → pour → observe → "Do it again" and saves a 1920×1080 recording.
3. Send the file; the edit swaps it in.

## Speed labels

Real footage that is sped up carries a small label (Real arm · 2×, app · 1.6×). Leave them in; judges trust a film that tells them what they are looking at.
