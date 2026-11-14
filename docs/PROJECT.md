# Project

OpenArms is a HackPrinceton prototype for accessible lab work. A student gives a voice command, previews the action in simulation, and confirms before it can run on the physical arm.

The SO-101 arms are calibrated and the repository has [teleoperation instructions](../firmware/README.md). See the [working project outline](../voice-lab-arm-outline.md) for background and ideas.

## First integration

Pick one lab action and use the same example across all four areas. Start by showing the command, preview, confirmation and mocked execution status. Bring in the physical arm when the firmware owner is ready to test the motion at the bench.

## Open decisions

- Which lab action should we demo first?
- What data does each area need for that action? Capture an example in [INTERFACES.md](INTERFACES.md).
- What can we show reliably at the bench, and what should the demo simulate?
