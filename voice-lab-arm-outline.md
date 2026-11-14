# Voice-Controlled Robotic Arm for Accessible Lab Work: Project Outline

> **Scope correction — demo-speed-v1:** [Architecture](docs/ARCHITECTURE.md) defines the target. The lesson/prediction/quiz sequence below describes existing or historical behavior, not a mandatory student workflow. Students choose individual physical actions. Preserve existing authorization and STOP while integrating the corrected flow; mock/simulation success is not physical demo completion.

> Working title. Our team's draft for scoping what to build, buy, and set up.

---

## 1. Motivation

### The problem
Wet-lab classes are hands-on almost by definition: pipetting, pouring, moving glassware. A student with a motor disability usually ends up **watching** a lab partner do the experiment and writing down the results. They get the data without the experience. They don't decide the next step, they don't make their own mistakes, and they don't get to say "I ran this."

A second group is shut out for a different reason, which is **distance**. Students in places without well-equipped labs (much of rural Africa and Asia, for example) can read about titration but rarely get to run one on real equipment at a strong university.

### The idea
A robotic arm that does the physical motions while the **student makes the decisions**. The student speaks a command ("pour 20 mL into beaker B"), sees it play out in a 3D simulation, approves it, and then watches the real arm do it through a live camera feed.

Voice is the accessibility layer. The web interface and camera are what let **anyone, anywhere** run the lab.

### Why now / why us
The closest prior work we found:
- **An NSF-funded voice lab assistant for blind students.** It had no arm and ended in 2024. *[add citation]*
- **A 1994 Stanford classroom robot.** *[add citation]*

Nobody we found has combined voice control, a physical arm, a simulator preview, and remote access in one system. Since 2024, low-cost open-source arms, browser-based 3D, and speech-to-text that runs well in a browser have all become cheap and easy to get, so a student team can build this now.

---

## 2. Use cases

### Use case 1: A student with a motor disability runs their own experiment
> The student opens the web app and speaks a command. The camera feed is linked in, and the arm performs the step.

1. Student opens the web app (in the lab or from home).
2. They say: *"Pour 20 mL into beaker B."*
3. The system repeats back what it understood and shows the move in the 3D sim.
4. Student says *"confirm"*, and the real arm executes while the camera streams it.
5. Student reads the result (scale readout, color change, etc.) and decides the next step.

### Use case 2: A remote student does labs at a top university
> The teacher sets up the physical lab on their end. Alongside it runs a simulator, where the student uses voice to try the procedure. If it looks right, they execute it on the real arm, with guardrails so anything too dangerous is blocked.

1. **Teacher** sets up the physical bench: arm, labeled positions, glassware, liquids.
2. **Student** (anywhere, any time zone) connects through the browser.
3. Student speaks commands and they run **in the simulator first**.
4. When the sim run looks right, the student asks to **execute on the real arm**.
5. **Guardrails** block anything unsafe, and a teacher or TA can stay in the loop as an approver.

### The pattern both share: simulate, then execute
Every command goes **voice → parsed command → sim preview → safety check → confirm → real arm**. That one pipeline covers both use cases. It is also our main safety mechanism.

---

## 3. System overview

```
 ┌──────────────────────── Browser (student) ─────────────────────────┐
 │  Mic ─► Speech-to-text ─► Command parser ─► Confirm UI             │
 │                                   │                                │
 │  3D simulator (digital twin) ◄────┤      Live camera feed(s) ◄──┐  │
 └───────────────────────────────────┼─────────────────────────────┼──┘
                                     ▼                             │
 ┌────────────────────────── Lab server ───────────────────────────┼──┐
 │  Session / control queue ─► Safety layer ─► Motion planner      │  │
 │                                                  │              │  │
 │                                          Arm driver  Camera streamer│
 └──────────────────────────────────────────────────┼──────────────┼──┘
                                                    ▼              │
 ┌──────────────────────── Physical bench ─────────────────────────┴──┐
 │  Robot arm · gripper · taped positions · glassware · scale · E-stop │
 └─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Components to set up

### 4.1 Hardware (physical bench)

| Component | Purpose | Options / notes |
|---|---|---|
| **Robot arm (5–6 DOF)** | Does the physical motion | Open-source and cheap: **SO-101** (Hugging Face LeRobot ecosystem). More robust: **myCobot 280**, **UFactory Lite 6**. Choose on payload: a full beaker plus gripper can weigh 300–500 g. |
| **Gripper** | Holds flasks and beakers | Parallel gripper sized for our glassware. Consider 3D-printed fingers shaped for one standard flask. |
| **Fixed bench layout** | Known positions instead of computer vision | Taped or printed mat with labeled spots (A, B, C, "pour station"). Positions are hard-coded and calibrated once. |
| **Glassware** | Experiment containers | Start with **plastic** beakers and a flask so a drop doesn't break anything. Use the same sizes everywhere so grip poses are reusable. |
| **Digital scale (load cell)** | Measures how much was actually poured | Load cell + HX711 under the target beaker. Water is ~1 g per mL, so "20 mL" becomes "stop at +20 g." **Strongly recommended:** open-loop tilt-pouring won't hit 20 mL reliably. |
| **Cameras** | Remote viewing and logging | (a) **Wrist camera** on the arm for close-up. (b) **Overhead/side camera** for the full bench, which remote viewers will want more. USB webcams are fine. |
| **Controller computer** | Runs arm driver, camera stream, server | A laptop or mini-PC by the bench. Raspberry Pi 5 can work for the driver plus streaming. |
| **Emergency stop** | Hard safety | A **physical** E-stop button that cuts arm power, plus a software stop in the UI. |
| **Spill tray** | Containment | Tray under the whole workspace. |

### 4.2 Simulation (digital twin)

| Component | Purpose | Options / notes |
|---|---|---|
| **Robot model (URDF/MJCF)** | Describes the arm's geometry and joints | Most open-source arms ship one (SO-101 does). |
| **Browser 3D renderer** | Shows the arm in the web app | **three.js** + `urdf-loader` is the easiest start. **MuJoCo (WASM build)** if we want real physics and collision. |
| **Bench scene** | Same layout as the real table | Model the taped positions and containers at measured coordinates. The sim and real bench must share **one coordinate config file**. |
| **Liquid visualization** | Shows pours | Fake it: animate a fill level instead of simulating fluid. That's enough for a preview. |
| **Sim ↔ real sync** | Twin mirrors the real arm | Stream real joint angles back so the sim shows the live arm state, not only previews. |

### 4.3 Voice and command understanding

| Component | Purpose | Options / notes |
|---|---|---|
| **Speech-to-text** | Mic → text | **Web Speech API** (free, in-browser, quality depends on the browser). **Whisper** (local or API) for accuracy and accents, which matters for international users. |
| **Command parser** | Text → structured command | Two ways: (1) a **grammar/regex** for a fixed vocabulary, which is predictable and easy to test; (2) an **LLM with structured output** mapping free speech to a fixed schema, which is more flexible. Either way the output is **one of a closed set of actions**, never free-form motion. |
| **Command schema** | The only things the arm can be asked to do | e.g. `pour(source, target, volume_ml)`, `move(container, to_position)`, `stir(target, seconds)`, `home()`, `stop()`. |
| **Read-back + confirm** | Avoid mishearing | System speaks and shows: *"Pour 20 mL from flask A into beaker B. Say confirm."* |
| **Non-voice input** | Accessibility goes beyond voice | Same commands from keyboard, buttons, and switch access. Some motor disabilities also affect speech. |
| **Text-to-speech feedback** | Status for users who can't watch the screen | "Pouring… done. Beaker B reads 20.4 mL." |

### 4.4 Web app

| Component | Purpose | Options / notes |
|---|---|---|
| **Frontend** | The student's interface | React/Svelte/plain JS. Panels: sim view, camera feed(s), command log, big confirm/stop buttons. |
| **Live video** | Low-latency camera feed | **WebRTC** for low lag, MJPEG for the quickest prototype. |
| **Realtime channel** | Commands and status | WebSocket between browser and lab server. |
| **Accessibility** | Use case 1 depends on it | Full keyboard navigation, screen-reader labels, large targets, high contrast, captions for spoken feedback. |
| **Experiment log** | Student owns their results | Timestamped log of commands, scale readings, and video clips, exportable for lab reports. |

### 4.5 Lab server / backend

| Component | Purpose | Options / notes |
|---|---|---|
| **Arm driver** | Sends joint commands | Vendor SDK or LeRobot for SO-101. **ROS 2** + `rosbridge` if we want standard tooling (more setup). |
| **Motion library** | Named, pre-tested moves | Each action (`pour`, `move`) is a **scripted, tested sequence** between known waypoints, not live free planning. This keeps behavior predictable. |
| **Session / control queue** | "Anyone can control" without chaos | **One controller at a time.** Others watch or wait in a queue, with a time limit per turn. |
| **Auth & roles** | Who can do what | Roles: **student** (sim + request execute), **teacher/TA** (approve, override, E-stop, edit bench config), **viewer**. |
| **Hosting** | Remote access | Lab server stays on the bench machine. Expose it through a tunnel (Cloudflare Tunnel, Tailscale) instead of opening ports. |

### 4.6 Safety and guardrails (cuts across everything)

Layered, so no single failure leads to harm:

1. **Language layer.** The parser can only output actions from the schema. Anything ambiguous gets a clarifying question instead of a guess.
2. **Lab-rules layer.** Allowlisted liquids (**water only** for the demo), max volume per container (no overfills), allowed source→target pairs, and a block on any action with a container not on the bench config.
3. **Simulation layer.** Every command runs in the twin first. Collisions, out-of-reach poses, or overflow in sim mean the command is blocked.
4. **Motion layer.** Joint limits, a workspace bounding box, keep-out zones (camera, scale, edges), and speed and acceleration caps, especially while holding liquid.
5. **Human layer.** Spoken/visual confirmation before every real execution. Remote mode can require **teacher approval** for real-arm runs. Physical and software E-stop.
6. **Network layer.** A heartbeat: if the controller's connection drops mid-action, the arm finishes or holds safely and does not continue a queue blindly.

> Open question: which experiments are "too dangerous" and who decides? Proposal: the teacher defines an allowlist per lab session. Default is deny.

---

## 5. Build phases

### Phase 0: Demo (our current target)
*"Pour 20 mL into beaker B" with water, taped positions, no camera.*
- [ ] Arm assembled, calibrated, homing reliably
- [ ] Bench mat with 3–4 labeled positions, coordinates recorded
- [ ] Scripted `move` and `pour` motions tested by hand
- [ ] Scale under target beaker for closed-loop pour
- [ ] Speech-to-text → parser → command for a small fixed vocabulary
- [ ] Read-back + confirm, E-stop working

### Phase 1: Web + simulator
- [ ] Web app with mic input and command log
- [ ] 3D sim of arm + bench from the shared coordinate config
- [ ] Sim preview before every real run
- [ ] Real joint states mirrored into the sim

### Phase 2: Camera + remote
- [ ] Wrist + overhead camera streaming to browser (WebRTC)
- [ ] Auth, roles, single-controller queue
- [ ] Remote access via tunnel; latency test from a far location
- [ ] Teacher approval mode

### Phase 3: Accessibility & real use
- [ ] Non-voice input paths (keyboard, switch, buttons)
- [ ] Text-to-speech status, screen-reader pass
- [ ] Multilingual speech (Vietnamese and others)
- [ ] Test sessions with students with motor disabilities, plus an accessibility office or disability services partner
- [ ] Exportable experiment logs

---

## 6. Risks and open questions

| Risk / question | Why it matters | Current thinking |
|---|---|---|
| **Pour accuracy** | "20 mL" has to mean 20 mL | Closed-loop with a scale. Report the actual measured amount back to the student. |
| **Arm payload** | Cheap arms can't lift a full beaker | Small volumes and light plastic glassware first. Check spec sheets before buying. |
| **Sim ≠ reality** | Preview is only useful if it matches | One shared config for positions. Calibrate regularly. Mirror real joint states. |
| **Latency for remote users** | Video lag makes it feel unsafe | The confirm-then-execute flow tolerates lag. No live joystick control. |
| **Speech errors / accents** | Wrong command = spill | Read-back + confirm. Whisper over browser STT for non-native English. |
| **Speech isn't accessible for everyone** | Some motor disabilities affect speech | Voice is one input method among several. |
| **Who is liable remotely?** | A real arm, real liquids, someone else's lab | Teacher present or approving. Water-only until there's a safety review. |
| **Does it feel like the student did it?** | The whole point of the project | Student makes every decision. Log attributes each action to them. Ask real users. |

---

## 7. What we still need to decide
- [ ] Which arm (budget vs. payload)
- [ ] Grammar parser vs. LLM parser (or grammar first, LLM later)
- [ ] three.js only vs. MuJoCo for collision checking
- [ ] ROS 2 or not
- [ ] First real experiment beyond the water demo (e.g. a simple color-change or dilution lab)
- [ ] Partners: disability services office, a chem/bio instructor, a remote school for a pilot
