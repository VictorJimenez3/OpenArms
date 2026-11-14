# OpenArms research to-do

Start with the first three experiments to choose a demo action and test the handoff from command to motion. Use “move the block from A to B” as a shared test input while the [demo action](../../docs/PROJECT.md#open-decisions) is open.

## First pass

- [ ] **Sim and mock arm — Does execution match what the student confirmed?** Preview A → B and confirm it. Repeat with a changed destination after preview, a rejected plan, and a preview timeout. Record the previewed and approved plan IDs, visible status, and executor calls for each case. Use the results to agree on the timeout behavior and capture one input and output in [Interfaces](../../docs/INTERFACES.md).
- [ ] **Bench — Can the SO-101 repeat one useful demo action?** With the firmware owner, run ten fixed-station block moves using the same start pose and layout. Record correct placements, cycle times, and where failures happen. If a water transfer is in scope, run it separately and measure delivered grams and spills. Use the results to pick the main demo and fallback.
- [ ] **Human walkthrough with mock execution — Does the student know what they’re approving?** Ask two teammates to act as students and one as the teacher. Give the students a task without telling them where to click. Try one correct preview and one with the wrong destination. Before they confirm, ask where the object will land and whether the arm has moved. Record whether they catch the mismatch, how they correct it, and whether the teacher can tell which plan is pending.

## Follow-up

- [ ] **Sim and mock arm — Can the voice flow distinguish a pause from a stop?** Try “wait five seconds,” “stop,” “move it over there,” and a clear A → B command in both quiet and room noise. Record the transcript, recognized intent, and whether the runner received a call. Use the typed versions of the same inputs to isolate speech recognition errors from interpretation errors. See the [plan actions and STOP behavior](../duc/harness.md#layer-2-plan-actions-the-only-things-a-plan-may-contain).
- [ ] **Mock arm — How long does a command take to reach the preview?** Repeat the same A → B command five times. Time the speech-to-text, plan generation, and preview stages separately. Record end-to-end times, timeouts, and the slowest stage. Repeat with the same typed command to see how much time speech adds. See the [Astranomy takeaway](../duc/harness.md#part-a-design-rules-from-astranomy).
- [ ] **Sim and bench — Where does the preview disagree with the real motion?** Compare the same approved block move and station layout in sim and on the bench. Record the destination, final placement, and any difference in clearance or timing. Try an out-of-reach target in sim and record how the failure is shown to the student.
- [ ] **Human walkthrough with mock execution — Can someone finish without the microphone?** Have a teammate complete the same task with keyboard input and report where they get stuck. Check command entry, preview, confirmation, and status. Save the steps that required help and any wording they misunderstood.

## Save the result

Before checking off an experiment, link a short note under the experiment owner's `research/` folder. Use the experiment question as the title. Include the date, setup and commit, evidence type (sim, mock run, bench, or teammate walkthrough), results with trial counts, and the decision the result supports. Include failed runs and link any logs or clips. Treat teammate walkthroughs as pilot feedback.
