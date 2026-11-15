# OpenArms Devpost submission

Final copy for team review · November 15, 2026 · paste section by section into Devpost. Bracketed notes are for us and must be deleted before submitting. Facts and sources: [pitch/FACTS.md](../../pitch/FACTS.md).

## Project name

OpenArms (Ollie)

## Elevator pitch (200 characters max)

You're the scientist. Ollie's the hands. A voice-directed robot lab partner for students who can't hold the beaker: it plans, asks before it moves, checks the result and remembers every skill.

## Main track and prizes

- Main track: **Education**
- Opt in: **Best Physical AI Hack** (Justin Bojarski), **Best Practical AI Innovation** (Amazon), **Best Hardware Hack**, **MLH Best Use of Gemini API**

## Story

### Inspiration

Every one of us is in STEM because a lab once made something click. But imagine knowing exactly what you want to test and not being able to hold the beaker.

One in five US undergraduates reports a disability, and only 8% ever register one with their college. In a national survey of students with physical disabilities, about half said they had been given passive roles in their science labs, and three in four relied on classmates to finish lab tasks. A partner can do the pouring. But when someone else has the hands, they usually end up making the calls too, and the student watches the experiment they were supposed to run.

We wanted the student to stay the scientist. So we built a lab partner that only does the hands.

### What it does

**Ollie** is a robot lab partner a student directs by voice.

1. **The student asks.** "Ollie, pour beaker A into flask C." They can talk, type, tap, or use the switch, eye-gaze or voice-control tools they already have.
2. **Ollie looks and plans.** It checks the bench through its camera and builds a plan from moves we have tested on the arm.
3. **Ollie says the plan and waits.** "Here's my plan. I won't move until you say yes." The student confirms, changes it or says no. Stop always wins, by button, Escape key or voice.
4. **The arm does it.** A real SO-101 arm picks up the beaker, pours, puts it back and returns home.
5. **The camera checks what actually happened.** Ollie reports what it saw, in words, and the student records their observation and explains it.
6. **Ollie remembers.** The first time, the AI reasons the task out step by step. Once it works and passes our checks, it becomes a saved skill. The next time, in any wording, it is one tool call: in our bench test, request-to-plan dropped from **58.8 seconds to 0.41 seconds**, and model calls from **six to zero**.

Every lab is a short inquiry: **Question → Predict → Direct Ollie → Observe → Explain.** The experiments come from a roughly $20 kids' science kit (Smartivity *My First Science Kit*): magic tea, an erupting volcano, magic potions, a lava lamp.

Not every school can buy a robot, so every experiment also runs in a physics simulation of the same arm, with the same conversation, the same plan-and-consent step and the same camera checks. **It personalizes to the student and scales to the school.**

### How we built it

**The agent loop (Python, FastAPI).** One session drives everything, from the browser or an iPhone.

- **Conversation: Gemini Live.** Real-time speech in and out, with barge-in, so Ollie can be interrupted mid-sentence and "stop" is heard immediately.
- **Expert planner: a separate vision-capable model** (Codex, Claude or Devin profiles, chosen per run and reported honestly in the developer view). It sees a fresh camera frame and composes a plan from a fixed set of typed, tested actions. It never sends motor commands.
- **Exact proposal and consent.** The plan becomes one exact, versioned proposal. Nothing runs until the student confirms that exact version, and a stale or reused confirmation is rejected.
- **Deterministic executor.** Only bounded actions reach the arm, inside its calibrated joint limits. Stop kills the run; late tool results and reconnects can't restart cancelled work.
- **Independent observer.** After every action a fresh frame is read by a separate checker that never sees the plan or the student's prediction, so "done" means "the camera saw it", not "the code finished".
- **Skill memory.** A successful plan is replayed by an evaluator on the normal case, six fault cases (missing, swapped, moved, occluded and stale views), the consent check and the Stop check. Only then is it saved, scoped to that exact bench setup. A changed bench means a fresh plan.

**The hardware.** An open-source SO-101 arm (about $122 in parts) on LeRobot. We designed a base plate in OpenSCAD with ArUco markers and rulers so vessels land in the same place every time, mounted an overhead camera with OpenCV localization, and taught the arm a real pour by hand with the leader arm. Recorded pours are corrected for small vessel offsets (0.5–4 cm) by solving how each joint must change, kept 3° inside the calibrated range.

**The simulation.** MuJoCo models of the same arm and bench. We lined the simulator up with the pour recorded on the real arm (grasp within 0.6 cm and 8°), so what Ollie rehearses on screen is what the arm does. The Smartivity experiments are modeled scenes with foam, colour-change and lava-lamp reactions, each clearly labelled as simulation.

**The student app.** A brand-new interface built around Ollie, a mascot drawn from the arm's own parts whose poses mirror what the arm is doing. Everything works by keyboard alone, with 48 px targets, no time limits, results read aloud and described in words rather than colour. An axe-core audit of 27 screen states found zero WCAG 2.2 A/AA violations. "Ask Ollie" answers science questions and declines everything else; the API key stays on the server.

[Credit before submitting: Hugging Face LeRobot and The Robot Studio (SO-101), MuJoCo, Google Gemini Live, OpenAI Codex, Anthropic Claude, Devin, FastAPI, OpenCV, Smartivity (experiments from *My First Science Kit*), Bagel Fat One and Atkinson Hyperlegible Next fonts, the music track. Note any pre-event planning and reused code.]

### Challenges we ran into

- **Latency.** Our first full loop spent most of its time thinking: almost a minute from request to plan. Skills, a guarded fast path and planning in one expert call got repeats under a second without skipping consent or the camera check.
- **Simulation versus reality.** A simulator that pours perfectly is useless if the real arm doesn't. We had to measure where the arm actually sits, recover its grip from a recorded pour and re-solve the simulation to match.
- **Making "done" true.** Code finishing is not the same as liquid in the flask. Building an observer that reads fresh pixels, rejects stale or swapped views and says "unknown" when it isn't sure took longer than the motion itself.
- **Accessible by default.** A voice-first app is not enough when the student's tools are switches, eye gaze or head pointers. We rebuilt the flow so every step is reachable one key at a time with nothing to drag, hold or hover.

### Accomplishments that we're proud of

- A student can direct a complete experiment, from prediction to explanation, without touching a mouse.
- The AI never moves the arm without an exact yes, and Stop always wins.
- Skills: the second time is **143× faster** to plan, with zero model calls.
- A real arm, a real fixture and a simulator that matches them.
- Zero automated accessibility violations across every screen, and 548 automated tests across the agent and simulator.

### What we learned

Directing an experiment is the learning, not a workaround. A student who specifies each step has to understand why it happens. We also learned that an agent earns trust by being boring at the right moments: say the plan, wait for yes, check the result, admit "unknown".

### What's next for OpenArms

- **Pilot with students and teaching staff.** Run a full lab with students who use assistive technology, with instructors deciding which choices count for the course.
- **Bring your own experiment.** Let an instructor photograph a lab handout and turn it into a guided Ollie lab, checked against the kit and the bench.
- **More hands, more labs.** Grippers and fixtures for pipettes, droppers and scales; physics, biology and chemistry stations.
- **A skill library that grows across schools.** Skills tested on one bench, shared to identical benches, each re-checked before use.
- **Simulation-first classrooms.** Every lab runnable without hardware, then "graduate" to the real arm in a supervised session.
- **Startup path:** a sub-$500 station kit, a per-seat simulation licence for schools, and disability-services offices and teaching labs as first customers.

## Built with

python, fastapi, gemini-live, google-gemini, openai-codex, claude, mujoco, lerobot, so-101, opencv, aruco, openscad, javascript, html, css, swiftui, playwright, axe-core

## Links

- GitHub: https://github.com/VictorJimenez3/OpenArms [confirm public and readable signed out]
- Video: [YouTube unlisted link, 2:00]

## Media

Gallery images, 3:2, in this order: (1) hero still of the real arm pouring with the Ollie app beside it, (2) the plan card "I won't move until you say yes", (3) New plan vs Saved skill cards, (4) base plate and overhead camera view, (5) four-up of the simulated experiments labelled Simulation, (6) the architecture diagram.

[Before submitting: replace "a real SO-101 arm picks up the beaker, pours" with exactly what the hero take shows. If the arm replays a recorded pour while the app runs the plan in simulation, write that in "What it does" step 4.]
