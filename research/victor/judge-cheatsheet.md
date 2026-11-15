# Judge cheat sheet (Amazon, Physical AI, Hardware, Gemini)

Education is covered in `hackprinceton-pitch-strategy.md`. This sheet is for the other judges. Sources: `research/victor/tracks/*.md` (what each sponsor said) and what we actually measured. Say only what ran.

## The one sentence (all judges)

"OpenArms lets a student with limited arm mobility run a real lab experiment by voice. The AI looks at the bench, proposes one exact action, the student confirms it, the arm does it once, and a separate camera check says what happened. The next time, the same request is saved and fast."

## What we can honestly claim (numbers are from our runs, simulator, scripted consent)

- New wording: about 13 s to the answer, 1 AI call. Same wording again or "do it again": about 9 s, no AI call.
- Safety: the student must confirm the exact plan; STOP works any time; one confirm = one move; success is judged by a camera check, never by the arm saying "done".
- Tests: 902 passed; 38 of 38 scripted scenarios (consent, faults, STOP) passed on the final code.
- Not yet done: the physical hand run on the final code, and a spoken test with a real microphone. Never say "tested on the real arm" unless that happens before judging.

## 1. Amazon: Best Practical AI Innovation

**What they value (4 equal parts, 25% each):** Creativity, Usefulness, Technical implementation, User experience. Their words: "AI someone would use every day, not AI that only works in a demo", and tools that "reason, plan, take action and adapt". No AWS needed. They require: working demo, a clear user and use case, basic docs, a pitch.

**Say:**
- Who and why: "A student who can direct an experiment but can't do the reach, grip or pour. Today they wait for someone else to do it."
- Reason, plan, act, adapt: "Our AI looks at the live scene, plans the steps, the arm acts, a camera checks. If you reword the request it still works."
- Gets better with use: "First time about 13 s with an AI call. After one success it saves the skill, so asking again takes about 9 s with no AI call."
- Easy to use: "You just talk. It reads the plan back and waits for 'confirm'."
- Reliable: "Wrong requests are refused with a reason, and you can say stop."

**Show:** one new request, then the same request again (watch the AI-call count go to 0).
**Don't:** claim the robot is fully autonomous, or that a fancy architecture alone is the point. Sponsor advice: start from the user's problem, keep it simple.
**Ask a judge:** "What would make you use this again next week?"

## 2. Justin Bojarski: Best Physical AI Hack ($500)

**What they value:** a physical hardware build with AI in it. Any domain. No stated rubric, so he is judging how real and how connected it is. In person on Sunday.

**Say:**
- "The AI's decision is what makes the arm move. Without it the arm would not know which action to take for the student's words."
- Name the AI job clearly: understands the request, looks at the scene, picks a safe action from what the arm can do, checks the result by camera.
- Honest limits: "The arm only does pre-tested moves. The AI chooses and checks them; it does not learn motor control." Justin may ask; answer plainly.

**Watch out:** a past winner (BRIDGE) was also "talk to a robot arm". Don't pitch it as just voice control. What is different: the student confirms every action, an independent camera check, an instant STOP, and saved skills that make repeats fast.
**Show:** the real arm moving from a spoken request, if it works. If it is only the simulator, say "simulated" out loud.
**Ask Justin:** "Does AI choosing among pre-tested moves count for you, or do you want learned motor control?"

## 3. Best Hardware Hack (event award)

**What they value:** hardware used creatively: robots, sensors, physical computing. No AI needed for this one. Judged on the general four: Creativity, Utility (does it work and do something real), Charity (human need), Avidity (enthusiasm, polish, plans).

**Say (Duc and Stef lead this one):**
- The build: SO-101 arm, the two-vessel fixture, calibration, and a pour recorded on the real arm that the sim is matched to.
- One concrete engineering problem and how you solved it (last year's winner won partly by explaining one: servo leverage on an extinguisher). Pick yours, for example matching the sim to the real pour, or making the arm hold the beaker reliably.
- Utility: "It does one real task start to finish and repeats it."
- Charity: "A student who can't do the hands-on part now directs it."

**Show:** the arm doing the pour, the fixture, and the recorded-pour match. **Don't** lean on the AI here; show the hardware working.

## 4. MLH: Best Use of Gemini API (if we opted in)

**What they value:** Gemini used for something real. **Say:** "Gemini Live is the voice: it listens, reads the plan back, hears 'confirm', and speaks the camera result. A separate AI plans the action." **Show:** a full spoken turn, including cancel and stop. Check Devpost that we opted in.

## If asked

- "Is this real or a simulation?" Answer first and clearly. Real arm: only what has actually run. Simulator: labeled simulated.
- "What if it goes wrong?" Nothing moves until you confirm; STOP any time; the arm moves once per confirm; unclear camera evidence means it stops and asks.
- "Is the AI just a wrapper?" No: it plans from the live scene, the host validates the plan, a separate camera check verifies, and good plans are saved and reused.
