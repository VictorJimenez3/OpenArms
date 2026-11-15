# Devpost submission · paste-ready

Copy each block into the matching Devpost field. Everything below is accurate to what we built and filmed; sources are in [FACTS.md](FACTS.md).

---

## Project name

OpenArms

## Elevator pitch (under 200 characters)

You're the scientist. Ollie's the hands. A voice-directed robot lab partner for students who can't hold the beaker: it plans, asks before it moves, checks the result and remembers every skill.

## Main track

Education

## Additional prizes to opt into

Best Physical AI Hack (Justin Bojarski) · Best Practical AI Innovation (Amazon) · Best Hardware Hack · MLH Best Use of Gemini API

## Video

[YouTube unlisted link] · if the talking heads aren't recorded in time, upload `pitch/renders/submit-safe-v3.mp4`

## GitHub

https://github.com/VictorJimenez3/OpenArms

---

## Inspiration

Every one of us is in STEM because a lab once made something click. Now imagine knowing exactly what you want to test and not being able to hold the beaker.

One in five US undergraduates reports a disability, and only 8% ever register one with their college. In a national survey of students with physical disabilities, about half had been given passive roles in science labs and three in four relied on classmates to finish lab tasks. A lab partner can do the pouring. But when someone else has the hands, they usually end up making the calls too, and the student ends up watching the experiment they were supposed to run.

We wanted the student to stay the scientist. So we built a lab partner that only does the hands.

## What it does

**Ollie** is a robot lab partner that a student directs by voice.

1. **The student asks.** "Ollie, pour beaker A into flask C." They can talk, type, tap, or use the switch, eye-gaze or voice-control tools they already have.
2. **Ollie looks and plans.** An AI expert checks a fresh camera frame and builds a plan from moves we have tested on the arm.
3. **Ollie says the plan and waits.** "Here's my plan. I won't move until you say yes." The student confirms, changes it or says no. Stop always wins: button, Escape key or voice.
4. **The arm does it.** Our SO-101 arm picks up the beaker, pours, puts it back and returns home.
5. **The camera checks what actually happened.** Ollie describes what it saw in words, and the student records their observation and explains it.
6. **Ollie remembers.** The first time, the AI reasons the task out step by step. Once the plan works and passes our checks, it becomes a saved skill. Next time, in any wording, it's one tool call: request-to-plan dropped from **58.8 seconds to 0.41 seconds**, and model calls from **six to zero**.

Every lab is a short inquiry: **Question → Predict → Direct Ollie → Observe → Explain.** The experiments come from a roughly $20 kids' science kit (Smartivity *My First Science Kit*): magic tea, an erupting volcano, magic potions and a lava lamp.

Not every school can buy a robot, so every experiment also runs in a physics simulation of the same arm, with the same conversation, the same plan-and-consent step and the same camera checks.

**It personalizes to the student and scales to the school.**

## How we built it

**The agent loop (Python, FastAPI).** One session drives everything, from a laptop browser or an iPhone.

- **Conversation: Gemini Live.** Real-time speech in and out with barge-in, so Ollie can be interrupted mid-sentence and "stop" is heard immediately.
- **Expert planner.** A separate vision-capable model (Codex, Claude or Devin profiles, chosen per run and shown honestly in the developer view) looks at a fresh camera frame and composes a plan from a fixed set of typed, tested actions. It never sends motor commands.
- **Exact proposal and consent.** The plan becomes one exact, versioned proposal. Nothing runs until the student confirms that exact version; a stale or reused confirmation is rejected.
- **Deterministic executor.** Only bounded actions reach the arm, inside its calibrated joint limits. Stop kills the run, and late tool results or reconnects can't restart cancelled work.
- **Independent observer.** After every action, a separate checker reads fresh pixels. It never sees the plan or the student's prediction, so "done" means "the camera saw it", not "the code finished". If it isn't sure, it says "unknown".
- **Skill memory.** A successful plan is replayed in simulation on the normal case, five fault cases (beaker missing, beakers swapped, beaker moved, camera blocked, stale picture), the consent check and the Stop check. Only then is it saved, scoped to that exact bench setup. A changed bench means a fresh plan.

**The hardware.** An open-source SO-101 arm (about $122 in parts) running on LeRobot. We taught it a real pour by hand with the leader arm, laid out red rulers and fixed stations, and mounted an overhead camera with OpenCV localization so it knows where each vessel is. Recorded pours are corrected for small vessel offsets (0.5–4 cm) by solving how each joint must change, always 3° inside the calibrated range. We also designed a printed base plate in OpenSCAD with ArUco markers for repeatable placement.

**The simulation.** MuJoCo models of the same arm and bench. We lined the simulator up with the pour recorded on the real arm (simulated grasp within 0.6 cm and 8° of the recorded one), so what Ollie rehearses on screen is what the real arm does. The Smartivity experiments are modelled scenes with foam, colour-change and lava-lamp reactions, each clearly labelled as simulation.

**The student app.** A new interface built around Ollie, a mascot drawn from the arm's own parts whose poses mirror what the arm is doing. Everything works with a keyboard alone: 48 px targets, no time limits, results read aloud and described in words rather than colour. An axe-core audit of 27 screen states found zero WCAG 2.2 A/AA violations. "Ask Ollie" answers science questions, declines everything else and keeps its API key on the server.

**Built with:** Hugging Face LeRobot, The Robot Studio's SO-101, MuJoCo, Google Gemini Live, OpenAI Codex, Anthropic Claude, Devin, FastAPI, OpenCV, OpenSCAD, SwiftUI and HyperFrames for the film. Experiments are adapted from Smartivity's *My First Science Kit*. Fonts: Bagel Fat One and Atkinson Hyperlegible Next.

## Challenges we ran into

- **Latency.** Our first full loop spent most of its time thinking: almost a minute from request to plan. Skills, a guarded fast path and single-call planning got repeats under a second without skipping consent or the camera check.
- **Simulation versus reality.** A simulator that pours perfectly is useless if the real arm doesn't. We had to measure where the arm actually sits, recover its grip from a recorded pour and re-solve the simulation to match.
- **Making "done" true.** Code finishing is not the same as liquid in the flask. Building an observer that reads fresh pixels, rejects stale or swapped views and admits "unknown" took longer than the motion itself.
- **Accessible by default.** Voice alone isn't enough when a student's tools are switches, eye gaze or head pointers. We rebuilt the flow so every step is reachable one key at a time, with nothing to drag, hold or hover.

## Accomplishments that we're proud of

- A student can direct a complete experiment, from prediction to explanation, without touching a mouse.
- The AI never moves the arm without an exact yes, and Stop always wins.
- Skills make the second request **143× faster** to plan, with zero model calls.
- A real arm, real fixtures and a simulator that matches them.
- Zero automated accessibility violations across every screen, and 548 automated tests across the agent and simulator.

## What we learned

Directing an experiment is the learning, not a workaround: a student who specifies each step has to understand why it happens. We also learned that an agent earns trust by being boring at the right moments. It says the plan, waits for yes, checks the result and admits "unknown".

## What's next for OpenArms

- **Pilot with students and teaching staff.** Run a full lab with students who use assistive technology, with instructors deciding which choices count for the course.
- **Bring your own experiment.** An instructor photographs a lab handout and Ollie turns it into a guided lab, checked against the kit and the bench.
- **More hands, more labs.** Grippers and fixtures for pipettes, droppers and scales, for physics, biology and chemistry stations.
- **A skill library that grows across schools.** Skills tested on one bench, shared to identical benches and re-checked before use.
- **Simulation-first classrooms.** Every lab runs without hardware, and students "graduate" to the real arm in a supervised session.
- **The business.** A sub-$500 station kit, a per-seat simulation licence for schools, and disability-services offices and teaching labs as the first customers.

## Built with (tags)

python, fastapi, gemini, gemini-live, openai, claude, devin, mujoco, lerobot, so-101, opencv, openscad, javascript, html5, css3, swiftui, playwright, axe-core, hyperframes

## Gallery images (upload in this order, from `pitch/gallery/`)

1. `01-arm-and-app.jpg`: the real arm pouring, next to the Ollie app
2. `02-plan-card.jpg`: Ollie planning from the student's words
3. `03-new-vs-saved.jpg`: "New plan · 1 AI expert call" next to "Saved skill · 0 AI expert calls"
4. `04-so101.jpg`: the SO-101 arm
5. `05-sim-grid.jpg`: the three simulated experiments, labelled Simulation
6. `06-ollie-home.jpg`: the Ollie home screen

## Team

Victor Jimenez · Duc Duong · Joseph Roche · Stefanie Nguyen. Add all four on Devpost, with Discord handles.
