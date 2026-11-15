# One pitch, five closers

The two-minute pitch is the film's script, live, with the arm pouring in front of the judge. Keep the spine the same for everyone (problem, live pour, skills, hardware, simulation) and spend the last 20 seconds on what that judge scores. Who answers follow-up questions is in [TEAM.md](TEAM.md).

| Judge | What they score | Our 20-second closer | Proof to point at |
| --- | --- | --- | --- |
| **Education** (main track) | Interactive, accessible, personalized learning | "The student owns the inquiry: they predict, direct, observe and explain. Ollie only does the hands. A student who specifies each step has to understand it; that's the learning." | The five-step lab bar in the app; Ask Ollie; the Access page; zero WCAG violations across 27 screens |
| **Justin Bojarski, Best Physical AI** | AI that really drives a physical build | "The AI picks the action, but never the motor command: it plans from tested moves, waits for yes, a deterministic executor moves the arm and a separate camera check decides if it worked. Then it remembers. BRIDGE showed language to an arm; we show an arm that asks, checks and learns." | Real pour; plan card; observer result; 58.8 s → 0.41 s |
| **Amazon, Best Practical AI** (creativity, usefulness, technical quality, UX at 25% each) | Reason, plan, act, adapt; someone would use it every day | "A specific user with a real problem. It reasons over the camera, plans, acts and adapts: a changed bench gets a fresh plan, a familiar one gets a saved skill. And the UX is a nine-year-old's vocabulary and one yes." | The full loop on screen; skill reuse; Stop; Access settings |
| **Best Hardware Hack** | Creative hardware integration that works | "A $122 open-source arm, taught by hand, with fixed stations, rulers and an overhead camera, offset correction 3° inside its joint limits, and a simulator lined up with the real pour." | The arm, the rulers, the camera view, real pour next to simulated arm |
| **MLH Gemini** | Meaningful use of Gemini | "Gemini Live is Ollie's voice: real-time, interruptible, and 'stop' is heard mid-sentence. The planner is a separate model, so conversation never waits on reasoning." | A spoken request and a barge-in Stop |

## Answers to the questions we'll get

- **"Isn't this just a script?"** The first time, the AI writes the plan from tested actions. Before it's saved, it's replayed against five failure cases plus consent and Stop. A different bench means a new plan. (Duc)
- **"Why not just a lab partner?"** A partner works; the research says the student usually ends up watching. Ollie keeps every decision with the student and never gets impatient. (Victor)
- **"Is the chemistry real?"** The motion on the arm is real. The reactions in the experiments marked Simulation are illustrative models, labelled as such. (Joseph)
- **"Is it safe?"** Supervised teaching labs only. Every motion needs an exact yes, joints stay inside calibrated limits, an operator stands by and Stop always wins. It's not certified for hazardous materials. (Stef)
- **"Has a student with a disability used it?"** Not yet. That pilot is our next step, and we built the app to WCAG 2.2 AA so it's ready for it. (Victor)
