# Can Rutgers execute the OpenArms SO-101 Isaac scene?

## Verified outcome — 2026-11-14

Yes. Final clean source `6afba01407b8036a0a22d5d8d6f261ac26424051` ran both
simulation-only science skills in Rutgers Slurm step **1273420.2**, host rlab7,
RTX A6000 / driver 580.178.04 / Isaac 5.1.0.0. Each recorded 720 frames (24 s),
passed contact-driven grasp/lift/carry/release/settling and exited zero. Repeated
fresh invocations reset the scene. The robot is white and has no onboard camera.

At fixed geometry, motion, friction and gravity, 10 g and 40 g conditions produced
measured settled support forces 0.098099999 N and 0.392399992 N. These are raw
simulator contact measurements, with analytic predictions separately labelled.
One final pair establishes a bounded demonstration, not physical performance or
statistical reliability. Earlier corrected trials at `002e9a7` also passed.

[Videos, full receipts, raw evidence bundle and reproduction](../../simulation/isaac/evidence/README.md)
include allocation identity, configuration, source, independent audit and logs.
The temporary passthrough VM was removed and the dedicated host restored without
replacing its installed driver. The canonical simulation skill interface is tested;
application backend registration remains separate integration work.

## Preserved earlier bring-up history

The following records the state before the qualified manipulation runs above.

On 2026-11-14, job `1273056` actually launched Isaac 5.1.0.0 on rlab7's RTX A6000
(driver 580.178.04), rendered the workshop SO-101 and recorded 240 H264 frames
at 960x720 / 30 fps. Rotation moved through 0.3613 rad. Commit:
`761a57974fa43af942b5a3b564413de2f7df1a5d`. The process then segfaulted in stage
cleanup (exit 139); the raw observation receipt's passed status is not a clean
job result. No grasp/place has been demonstrated. Shared evidence:
`/common/users/jdr317/openarms-isaac/evidence/job-1273056` plus
`slurm-1273056.log`. Video SHA256:
`b19fdfa21ff283a78fe22c2f9d2526d0f8b04d44af1c79fbdc5b73c7ba2903de`.

The user requested a white robot without an onboard camera. The next run uses
`SO-ARM101-USD-NO-CAMERA.usd` with only printed-plastic material overridden.
Composed geometry has no camera-named prims; 11 offline kinematics tests pass.
These are not evidence that the new configuration has run in Isaac. The exact live
queue and installation state are tracked in [issue 15](https://github.com/VictorJimenez3/OpenArms/issues/15).

The [runtime runbook](../../simulation/isaac/README.md) contains executable
bootstrap, GPU preflight and recording instructions. Its smoke is explicitly
articulation-only. Synthetic acceptance checks reject preplaced objects,
one-finger pushing, below-receiver poses, unsettled objects and invalid data;
they do not prove physics execution.

Initial raw attempts: A6000 allocation `1273052` could not start because GPUs
were busy. CPU install `1273054` failed because a shallow Git bundle could not
be cloned. Transfer was corrected with an exact shallow deployment checkout;
CPU install `1273055` and dependent GPU smoke `1273056` were then submitted.
Install `1273055` failed on a stale NFS script handle; an immutable node-local
script retry, `1273059`, completed successfully, and the GPU dependency was
repaired before job `1273056` ran. Do not edit scripts while a node reads them
over NFS.
CPU host check `1273057` verified Ubuntu 24.04.4, glibc 2.39, NVIDIA kernel driver
580.178.04, Vulkan/NVIDIA GLX/EGL/NVENC libraries, and 10 TB free node-local
storage on rlab7. This host check had no allocated GPU and is not an RTX test.

NVIDIA workshop pin: `ce807d99724cb65671abec01f908a2fcb4a6eab7`. Real LFS assets
were downloaded and inspected with OpenUSD on the Mac. Root units are metres,
Z-up; `/so101_new_calib/base` is the articulation root, the base has a fixed
joint, and six named revolute joints match the workshop action configuration.
Inspection is static asset evidence, not simulator evidence.

Prior project context: [Notion source snapshot](../joseph/OpenArms-Complete-Notion.md)
and [educational simulation research](../victor/educational-simulation.md).
The currently fetched architecture selects Isaac exclusively for this work.
The physical robot and existing MuJoCo work are untouched.
