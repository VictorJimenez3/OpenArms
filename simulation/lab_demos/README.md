# Four tiny MuJoCo laboratory demonstrations

The selected presentation experiments are color comparison, single-step dilution, stirred-versus-still dissolution, and titration. Each experiment owns its apparatus, policy, scientific model, recording command, tests, and evidence in its subdirectory. Original static Blender design candidates remain in `visual_assets/classic_lab/`; filtration and precipitation are outside this video scope.

The robot is the existing licensed SO-101 model. Scientific responses are declared simplified models, not physical laboratory measurements. Read each experiment README for its controller mode, engagement checks, assumptions, and reproducible command. Video playback may be accelerated; elapsed model time and playback speed must remain explicit.

| Experiment | Robot action | Observation |
| --- | --- | --- |
| [Color comparison](colorimetry/README.md) | Place prepared samples in a reader | Modeled optical readings |
| [Single-step dilution](dilution/README.md) | Operate a fixed water dispenser | Added volume and concentration versus untouched control |
| [Dissolution](dissolution/README.md) | Activate one stirrer | Remaining solid versus still control at equal elapsed time |
| [Titration](titration/README.md) | Deliver metered doses | Indicator endpoint and accumulated dose |

These are simulation demonstrations. They do not qualify real robot motion or change the physical pH demo scope.
