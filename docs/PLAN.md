# OpenArms first integration plan

Use a fixed-station block transfer as the proposed first shared test. Pick the judge demo after the bench runs. The red-cabbage pH demo is still a candidate if the team can repeat the transfer and show the observed result. See the [team architecture brief](https://app.notion.com/p/41771c9c107e8141bba0d7beb491601b) and [demo runbook](https://app.notion.com/p/41771c9c107e81ab8026cdafa6245063).

## What each part owns

Student command → validated plan → preview → student confirmation and any required instructor approval → executor → result.

| Area | First handoff |
| --- | --- |
| UI · Victor | Accept typed input first and add voice after the first mock run. Show the destination, preview, confirmation, any instructor feedback, and execution status. [UI architecture draft](https://github.com/VictorJimenez3/OpenArms/pull/6) |
| Agentic · Duc | Validate the named action and stations. Track which plan was previewed and confirmed, and call the executor only for the approved plan. |
| Simulation · Stefanie | Preview that plan against the same station layout the executor uses. Return the plan ID and either a preview or an explicit failure status. |
| Firmware · Joseph | Specify the station layout and reset position. Map supported transfers to taught poses on the SO-101. Report the motion result and support a direct stop. |

Keep movement fixed for this test. The student can choose a supported destination. The model translates that choice into a named action, and the executor supplies the taught motion. Free-form distances can wait until a bench task actually needs them. See [Duc's harness](../research/duc/harness.md#layer-4-preprogrammed-scripts-joseph-firmware) and the [arm setup](../firmware/README.md).

## One example for all four areas

1. Type “Move the block from A to B.” The agent validates a plan such as `p1 = move_block(A, B)` for a fixed test layout. The preview shows the block ending at B and returns status for `p1`.
2. The student confirms `p1`. If the instructor rejects it with “Use C for this trial,” show that comment and make no executor call.
3. The student requests C. Create `p2 = move_block(A, C)` and preview it. The new plan requires its own student confirmation and, when required, instructor approval. The mock executor should get exactly one call, for `p2`, even if approval is submitted twice.
4. Show whether the run was mocked or physical. On the bench, report motor completion and observed placement separately.

C is a mock destination for testing revision. The first physical rehearsal can use a single taught A → B transfer. `move_block` illustrates a test fixture. Duc's [draft catalog](../research/duc/agentic-plan.md#finding) uses `add_sample`, `wait`, and `look`. Agree on the action name and record one input, output, and acceptance check in [INTERFACES.md](INTERFACES.md).

## Build and check

Claim work by assigning yourself on the issue. Track progress and evidence there.

1. **Agree on the first handoff.** Pick the test action and record the example and approval behavior in [INTERFACES.md](INTERFACES.md). [Issue #9](https://github.com/VictorJimenez3/OpenArms/issues/9)
2. **Mock the whole flow.** Start with typed input and a mock arm. Use a fake preview response until the simulation adapter is ready, then run the same case against it. Check approval, rejection, a changed plan, and timeout. Log plan IDs and executor calls. [Issue #10](https://github.com/VictorJimenez3/OpenArms/issues/10)
3. **Set up the bench in parallel.** Pick the object, gripper, starting pose, and marked tray positions. Reset to the same setup and run ten A → B transfers. Log correct placements, duration, and the failed step for each miss. [Bench checklist](../research/joseph/TODO.md#first-pass) · [Issue #11](https://github.com/VictorJimenez3/OpenArms/issues/11)
4. **Rehearse with the arm.** Once the mock and bench checks are complete and the approval rules are agreed, run one spoken command through preview, explicit confirmation, and physical execution. Have a teammate check the observed placement against the preview. [Issue #12](https://github.com/VictorJimenez3/OpenArms/issues/12)

The [iPhone voice bridge](https://github.com/VictorJimenez3/OpenArms/pull/5) combines the iOS client and Mac relay in a draft PR. It runs a simulated lab. If the team uses the bridge, adapt the agent to the relay's asynchronous dialogue call with session and turn IDs. The agent owns which plan can execute. A relay transcript or playback acknowledgment carries no execution authorization. [Device verification · issue #4](https://github.com/VictorJimenez3/OpenArms/issues/4)

## Decisions to confirm

- **Who authorizes a run?** The repo brief calls for student confirmation. Duc's draft requires synchronous teacher approval before motion. Confirm whether both are required for every live demo action. Use the reject-and-revise example to check what each person sees.
- **What happens when preview is unavailable?** The [repo brief](PROJECT.md#first-integration) puts preview before physical execution. The [team architecture brief](https://app.notion.com/p/41771c9c107e8141bba0d7beb491601b) and [agentic plan](../research/duc/agentic-plan.md#finding) describe continuing to instructor approval after a timeout. For the first physical integration, the proposed behavior is to show “Preview unavailable,” let the student retry, and hold motion until there is a valid preview. Test the timeout with a mock and agree on the live behavior in the shared interface.
- **What goes in front of judges?** Choose after the bench runs. The in-person run can demonstrate the student directing the experiment. A separate laptop can illustrate remote participation if it helps the story.
