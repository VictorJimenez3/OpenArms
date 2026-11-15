# Facts we can say out loud

Checked November 15, 2026. Use the wording in the left column; it matches what the source supports. Longer evidence and counterevidence: [accessibility research](../research/victor/accessibility-market-validation.md).

## The problem

| Say | Source | Careful |
| --- | --- | --- |
| **1 in 5 US undergraduates reports a disability** (20.5% in 2019–20). | [NCES Fast Facts](https://nces.ed.gov/fastfacts/display.asp?id=60) | Covers all disabilities, most of them not motor. Use it for scale, not as "1 in 5 can't pour". |
| **Only 8% registered a disability with their college** that year. | [PNPI fact sheet, citing NCES](https://pnpi.org/wp-content/uploads/2026/02/PNPI_StudentswithDisabilities_FactSheet_Jan26.pdf) | Shows many students never get an accommodation at all. |
| **In a survey of 107 students with physical disabilities, about half had been given passive roles in science and engineering labs**, and a quarter hit a barrier just entering the lab. | [Jeannis et al., *Disability and Rehabilitation: Assistive Technology*, 2019](https://www.tandfonline.com/doi/full/10.1080/17483107.2018.1559889) | Purposive sample, self-report. Say "in one national survey". |
| **47% felt no practices were in place to accommodate them** in the lab; 74% relied on peers to finish lab tasks. | same | The 74% is why "a partner pours" is the status quo we improve on. |
| **People with disabilities earn 11% of US science and engineering doctorates but are 3% of the STEM workforce.** | [NSF NCSES, Diversity and STEM 2023](https://new.nsf.gov/news/diversity-and-stem-2023) | Pipeline framing for the Charity criterion. |
| A Butler chemistry student who directed an assistant through organic labs said **specifying each action helped him understand the labs**. | [Esteb et al., 2016](https://www.researchgate.net/publication/291152783_Accommodations_in_the_Organic_Teaching_Laboratory_for_Students_with_Mobility_Issues) | One case. It supports "directing is learning", which is our whole design. |
| University College Cork bought a lab robot specifically so students with disabilities could complete biochemistry labs. | [UCC, 2022](https://www.ucc.ie/en/sefs/news/2022/robots-will-help-students-with-disabilities-complete-lab-classes.html) | Proof that schools pay for this. Their robot pipettes only; it doesn't talk, plan or adapt. |

## Cost and scale

| Say | Source |
| --- | --- |
| **The SO-101 follower arm is about $122 in parts** (open-source BOM); assembled leader-and-follower kits sell for about $260–300. | [SO-ARM100 repository BOM](https://github.com/TheRobotStudio/SO-ARM100/) · [price tracker, checked Nov 15](https://openrobotkits.com/robots/so-101/) |
| **The closest lab robot schools already buy, the Opentrons OT-2, starts at $15,950.** | [Opentrons](https://opentrons.com/products/ot-2-robot) |
| **The experiments come from a roughly $20 kids' kit** (Smartivity My First Science Kit). | Team purchase; keep the receipt. Credit Smartivity by name. |
| A 35-study meta-analysis found **no significant overall difference in conceptual learning between physical and virtual inquiry labs**. | [Muilwijk and Lazonder, 2023](https://doi.org/10.3389/feduc.2023.1163024) | This is why simulation is a real option, not a consolation prize. It also means "real" has to earn its place: real variation, real results. |

## What we built (our own evidence)

| Say | Where it comes from |
| --- | --- |
| **58.8 s → 0.41 s** from request to exact plan when a saved skill is reused; **6 model calls → 0** for the whole run. | Duc's logged MuJoCo demo-bench run with a live Claude expert, `research/duc/demo-bench-integration.md`. Simulator timing. |
| In the student app today: **"New plan · 3.9 s · 1 AI expert call"** then **"Saved skill · 0.5 s · 0 AI expert calls"**. | Recorded from the running app at 5:00 a.m. on Nov 15 (`openarms-film/footage/app/`). Fast path on, simulation backend. |
| Before a skill is saved, it is replayed on the normal case, **six fault cases** (missing, swapped, moved, occluded, stale camera), the consent check and the Stop check. | `research/duc/demo-bench-integration.md`, setup-scoped evaluator. |
| The simulator was lined up with a pour recorded on the real arm: solved grasp within **0.6 cm and 8°** of the recorded one. | Stef's commit `db1da78`. The pour pose is 4 cm and 17° off; don't quote that one as "matched". |
| The student app passed an automated accessibility audit (axe-core, WCAG 2.2 A/AA rules) across **27 screen states with 0 violations**; everything works by keyboard, switch, voice control or eye gaze. | `ui/student/DESIGN.md` on `victor/user-flow-ui`. Automated rules only; not yet tested with real assistive-technology users. |
| **548 automated tests**, **315 commits** on main. | `rg -c "def test_"` over `agentic/tests` and `simulation/tests`; `git log` on main, Nov 15. |

## Do not say

- That we tested with students with disabilities, or measured learning. We haven't yet.
- That Ollie is safe for hazardous chemicals, or certified for anything.
- That the AI controls the motors directly. It chooses from tested, bounded actions; a deterministic executor moves the arm.
- That the simulated reactions are measured chemistry. They are illustrative models.
- Any wet-chemistry result on the real bench that the team did not actually see.
