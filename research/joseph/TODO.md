# OpenArms current tasks

Reconciled November 14, 2026 against main `4f9c3ec` and Joseph's current two-vessel decision. [PROJECT](../../docs/PROJECT.md) owns experiment scope, [TEAM_WORK_PLAN](../../docs/TEAM_WORK_PLAN.md) ownership, and [MAIN_INTEGRATION](../../docs/MAIN_INTEGRATION.md) merge/evidence status. Existing issues and the [shared Master TODO](https://app.notion.com/p/41871c9c107e81d5b6fdfcb4ab71fdd5) track the same work. “Done” below is bounded to the stated evidence, never physical qualification by implication.

## P0 — physical and integration

| Status | Outcome / owner | Acceptance / next action |
| --- | --- | --- |
| Done — decision | Two-vessel physical scope / Joseph | A donor → C stationary receiver → return A → HOME; preferred tea/citric acid, fallback contained fizz. Chemistry adaptation remains unverified. |
| Doing / Waiting On physical measurements | Actual vessel selection and geometry / physical team + existing fixture lane · #12 | Photo-derived models are on main via PR #23, refined to v2 in PR #24 (`e3ede414`). Confirm dimensions with actual vessels and retain uncertainty; underside `100ml.` is not a fill line. |
| Doing | Two-vessel fixture and fiducials / Model two-vessel base plate · #12 | Consume this existing lane's CAD, marker IDs/dimensions and machine-readable transforms. Printed fit, jaw clearance and robot registration await physical checks; old four-slot export is historical. |
| Waiting On supervised bench evidence | First repeatable dry/water A→C pour / Victor, Duc and physical team · #12 | Record donor pickup, delivery/spill, return, HOME, failed attempts and repeat/reset. Preserve calibration/poses; no unattended motion. |
| Waiting On physical handoff | Register the physical skill and semantic mapping / coordinated runtime + firmware owners · #9, #10, #12 | Bind actual A/C identities, setup/calibration/pose versions, bounded portion and observation checks. Main application currently has physical dispatch disabled. |
| Doing — separate prototype | Camera-aware expert / Joseph + coordinated runtime lane · #10, #19 | Review/port the existing camera adapter; real capture IDs/time/configuration/provenance and stale/moved/missing/swapped rejection. Live physical camera qualification remains open. |
| Waiting On actual inventory and trial | Selected recipe and visible outcome / physical team · #12 | Magic Potion 1 manual pages 30–31 reviewed in shared Notion. Check actual packets, preparation and two-vessel adaptation; verify preferred visible response or fallback. Water for nearly all calibration. |
| Done — bounded software/live-provider evidence; Doing — acceptance | Responsive student interface / voice/client owners · #4, #10 | PR #25: real Gemini Live generated speech, correction, exact consent, mock STOP/barge-in; 529 Python + 36 browser + 5 audio checks. Keep speech working. Human Mac audibility and unplugged iPhone remain unverified. |
| Not Started — physical acceptance | First-minute student action and truthful outcome / integrator + physical team · #10, #12 | Time actual command/acknowledgment/authorization/first motion/result, record interventions and failures. Optional prediction/reflection; no compulsory simulator preview. |

## P1 — simulation and skill improvement

| Status | Outcome / owner | Acceptance / next action |
| --- | --- | --- |
| Doing — prototype unmerged | Two-vessel MuJoCo configuration / Joseph + existing simulation lane · #19 | Reuse separate `f1cf4fd` prototype after review, retaining current speech. Match donor/receiver and return/HOME; reproducible reset and explicit geometry uncertainty. Main still has older fixed-dispenser regression scene. |
| Doing | Matching camera/fixture representation / simulator + fixture owners · #9, #19 | Consume agreed reference geometry and IDs. MuJoCo active; Isaac parked. Optional volcano scene may use extra vessels; never expand physical scope silently. |
| Doing / Waiting On fixture output | Fiducial geometry and localization / fixture lane + camera consumer · #9, #12 | High-contrast printed marker patterns, IDs/sizes/corners, plane/fixture frame and invalid/missing-marker tests; robot registration remains physical work. Recessed letters/rulers do not qualify. |
| Doing | Fresh scene tools and failure behavior / Joseph + runtime/perception owners · #10, #19 | Verify on-demand capture, configuration mismatch, stale/moved/missing/swapped cases, UNKNOWN, cancellation and delayed-result rejection. Capture FPS and inference/motor cadence stay independent. |
| Done — prior regression only; Doing — two-vessel acceptance | Cold/warm reusable skill / runtime + integrator · #19 | Retain existing regression evidence; establish equivalent two-vessel cold/warm task, independent outcome and source/scene-specific admission without needless warm expert calls. |
| Doing — evaluation capability only | One real measured improvement / Improve harness self-improvement · #19 | Initial evaluator `3f47ada` is not D4. Retain unchanged baseline, actual limitation, substantive revision, comparable held-out cases, failures, latency/success and rollback. |
| Doing | Connected integration smoke and independent review / existing coordinator · #10, #19 | Fresh observation → skill → MuJoCo → independent result → warm reuse; exact consent and STOP/reconnect regressions; record commit and backend. Keep physical claims separate. |

## Optional after the primary demonstration

- Swapped cup positions or arbitrary localization beyond the fixed two-vessel setup.
- A second recorded physical chemistry demonstration after the first works.
- Additional simulation experiments/Devpost material, including the existing volcano lane's broader scene.
- Learned localization, imitation/policy training or other research justified by measured need.

## Evidence and historical research

Keep [consolidation receipts](software-consolidation-2026-11-14/README.md), [actual Gemini conversation receipts](gemini-conversation-2026-11-14/README.md), [mandarin evidence](mandarin-transfer-2026-11-14/README.md) and [vessel-model provenance](../../simulation/models/vessels/measured_2026_11_14/README.md). Prior A→B block-preview, buoyancy and replacement-voice tasks are superseded as active priorities; their original plans and receipts remain in Git/research history.

Before marking acceptance done, retain date, exact code/setup/calibration versions, evidence type, trial counts, failures/interventions, result and decision in the existing owner's research folder. Human walkthroughs are pilot feedback; generated speech is not device audibility; simulation is not physical qualification. Update existing issue status and shared Notion after evidence review.
