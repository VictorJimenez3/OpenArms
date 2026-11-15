# Directives: the last three hours

Sunday, November 15 · Devpost hard cutoff **8:00 a.m. ET** (rules; the header says 8:30, ignore it) · in-person judging 9:30 a.m.–2:00 p.m.

**Your lines and how to record them: [SCRIPTS.md](SCRIPTS.md).** Film plan: [FILM.md](FILM.md). Facts and sources you can say out loud: [FACTS.md](FACTS.md). Devpost copy: [DEVPOST.md](DEVPOST.md).

## Schedule

| By | What | Who |
| --- | --- | --- |
| 5:45 | Bench dressed: white backdrop, A and C with coloured water, cables hidden, lab coats on | Stef, Duc |
| 6:30 | Shots H1–H10 and T1–T4 filmed and AirDropped to Victor's Mac (`openarms-film/footage/hand/`) | Victor films, Stef and Duc on the arm |
| 6:30 | Four talking-head takes (`talk-<name>.mp4`, see SCRIPTS.md), the opening skit and one music track sent to Victor | everyone; Joseph picks music |
| 6:30 | Repository public and readable signed out, README merged | Victor |
| 7:15 | First full cut rendered | Devin |
| 7:30 | Team watches once with sound; one round of fixes | everyone |
| 7:40 | Upload to YouTube as **Unlisted**, paste link in Devpost | Victor |
| 7:50 | Devpost submitted, all four members added, tracks selected, status shows Submitted | Victor, Joseph checks |

## Victor: problem, product and agent

- **Say:** the problem and product lines in FILM.md (0:07–1:00) and the close.
- **Film:** you hold the phone for H1–H10 unless Joseph is free.
- **Decide by 5:45:** does the hero take run the arm from the app (bench lane, operator `y` in the terminal), or does the arm replay Stef's recorded pour while the app runs the same plan in simulation? Either is fine; the labels in FILM.md change with it.
- **Before 6:30:** make `VictorJimenez3/OpenArms` public, or name the public repo. Check it signed out. Scan it for `.env`, tokens and personal data first; the Ollie chat key must stay in `.env` only.
- **Pitch:** you open and you take the agent questions (Amazon and Justin). Draw the loop on the whiteboard: voice → Gemini Live → expert with camera → exact plan → yes → executor → camera check → skill saved.

## Duc: skills and memory

- **Say:** the skills lines (1:00–1:20). Your number is yours: 58.81 s to 0.41 s request-to-plan, 6 model calls to 0, from `research/duc/demo-bench-integration.md`.
- **Film:** T2 (your first line on camera) and help Stef on the arm for H2–H4 and H9.
- **Pitch:** own the "how is that different from a script" question. Answer: the AI writes the plan the first time from tested actions; the evaluator replays it on the nominal case plus six fault cases, the consent check and the Stop check before saving it; a saved skill is tied to that exact bench setup, so a changed bench means a fresh plan; consent and the camera check still run on every repeat.

## Stef: arm and hardware

- **Say:** the hardware lines (1:20–1:40).
- **Film:** you run the arm for H1, H2–H4, H5 (your hands on the leader arm), H9 and H10. Operator stays at the arm with a hand near Stop for every motion; no unattended motion.
- **Bring:** one screen recording of the real pour you recorded next to the matching MuJoCo replay (your `db1da78` work). That split screen is the single best proof that the sim matches the hand.
- **Pitch:** own the Best Hardware Hack questions: base plate design (OpenSCAD, ArUco IDs 20–23 at 27 mm), why rulers and markers, camera placement, recorded-pour offset correction (0.5–4 cm), joint limits kept 3° inside the calibrated range.

## Joseph: simulation and the science

- **Say:** the scale lines (1:40–1:52).
- **Do by 6:30:** pick the music track (licence link in `audio/CREDITS.txt`); check that the clean renders in `openarms-film/footage/sim/` show your experiments correctly; render Magic Snow clean if you have its episode states.
- **Pitch:** own Education and the chemistry: what the student learns (acid plus base makes a gas; indicators change colour), why prediction → observation → explanation, and why simulation is labelled as a model.
- **Check Devpost** before 7:50: four members, Education as the main track, Amazon, Best Physical AI, Best Hardware and Gemini opt-ins, video and repo links open in a private window.

## Everyone

- Lab coat and goggles in every shot, in the video and at the table.
- Say "simulation" when it is simulation. Never claim we tested with students, measured learning or certified safety.
- The two-minute table pitch is the film's script live, with the arm doing the pour for real in front of the judge. If the arm is not reliable, run the app in simulation and play the film's hardware section.
