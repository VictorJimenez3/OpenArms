# OpenArms Devpost draft

Draft for team review · November 15, 2026

## Project name

OpenArms

## Tagline

A voice-interactive science lab prototype with a supervised robot bench and reusable AI skills.

## Inspiration

A student can understand the experiment, decide what to test and still need help reaching or pouring the materials. We wanted to build a way for students with limited hand or arm mobility to direct those actions themselves in a supervised teaching lab, hear what happened and choose the next step.

## What it does

OpenArms lets a student ask for a lab action in ordinary language. The student can review and confirm the proposed action, correct it, ask for progress or stop. The system checks the scene and reports the observed outcome in plain language. We tested the conversational controls in MuJoCo, where students can explore modeled conditions and reactions. Separately, we demonstrated a supervised SO-101 transfer on a physical bench. We are working toward connecting student speech to a qualified experiment with real materials.

When OpenArms encounters an unfamiliar request, a background AI expert can inspect the scene and compose a plan from supported actions. A successful plan can become a tested skill for that setup. When a student asks for the equivalent action again, the system can reuse the skill and get to the next experiment faster.

## How we built it

Gemini Live handles conversational speech. A separate expert uses images and tools to propose a precise action. A deterministic executor handles supported motion after confirmation and a separate observer checks the result. The evaluator and registry keep reusable skills tied to the setup where they were tested. The checks still apply when a saved skill is used. We built and rehearsed with the SO-101, MuJoCo and experiments adapted from Smartivity’s *My First Science Kit*.

## What we tested

In one typed MuJoCo bench rehearsal, the expert took 58.81 seconds to produce the first proposal. After the skill was tested and saved, an equivalent request with different wording took 0.41 seconds to reach a proposal. Across each full run, expert model calls went from six to zero. Both trials produced an independently observed simulated result. We separately tested Gemini Live conversation with generated student audio in a water-only simulation. Our recorded Smartivity simulations show modeled color mixing and effervescence.

## What's next

We want to rehearse a complete lab activity with students and teaching staff, from directing the first action to assessing the result and trying another condition. That would let us check whether students can correct and stop actions easily, whether spoken observations give them what they need, and how much bench preparation and reset the activity requires.

## Team editing before submission

- Add the exact result for the qualified live trial. If the full voice-to-arm path passes, name the spoken command and the real observation. If the team executes a supervised bench action separately, name the operator handoff. If wet chemistry stays unverified, describe the qualified physical motion or prior dry transfer and label the reaction evidence as simulation.
- Identify the actual expert and tools the published demo uses. Credit external code, assets, Smartivity and supporting frameworks in the README and Devpost. Record the team's event-built contributions. Keep private team notes, credentials and unnecessary device data out of public material.
- Show the real bench or genuine rehearsal first in media. Caption the recordings. Put “SIMULATED” on all virtual outcomes and identify the scripted Lava Lamp if included. Keep the optional video under two minutes.
- Use the [track and submission checklist](hackprinceton-pitch-strategy.md#submission-decisions) for the public repo URL, cutoff, team and prize entries. These notes support the team submission. Paste only the final approved copy into Devpost.
