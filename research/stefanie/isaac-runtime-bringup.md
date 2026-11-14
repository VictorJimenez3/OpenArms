# Can Rutgers execute the OpenArms SO-101 Isaac scene?

As of 2026-11-14, access and CPU installation are established; actual RTX
allocation, Isaac launch and grasp/place remain unverified. The exact live
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
