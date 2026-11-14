# Four tiny MuJoCo laboratory videos

The selected scope is color comparison, single-step dilution, stirred-versus-still dissolution, and titration. Filtration and precipitation are retained only as earlier Blender design references. The four selected implementations rebuild simple apparatus around the existing licensed SO-101 MuJoCo model; they do not import the earlier USD scenes or depend on Isaac.

Four isolated Account 1 CLI workers implemented the experiments in parallel after Account 2 rejected launches for exhausted usage. The coordinating agent completed the colorimetry worker's timed-out handoff, corrected dilution volume geometry and initialization, improved dissolution transparency, reviewed actual frames, and integrated the four branches. Source, commands, videos and controls are in [the demo package](../../simulation/lab_demos/README.md).

## Executed simulation evidence

- Color comparison: both prepared samples are grasped, brought to the reader, read, and returned. The material-RGB optical proxies are 0.5738 and 0.7400. Disabling the reference pickup withholds its measurement and the two-sample comparison. The grasp uses geometric engagement followed by mocap attachment; optical data is a material proxy, not camera pixel sensing.
- Dilution: one robot-triggered 20 mL water dose increases the treated sample from 20 to 40 mL, reducing modeled relative concentration from 1 to 0.5 while conserving dye amount. The control remains unchanged. Disabling dispensing produces zero added volume and no concentration change. The displayed liquid height uses milliliters converted to cubic meters.
- Dissolution: robot activation enables the stirred rate only after reaching the switch zone. After 180 model seconds, remaining solid fractions are about 0.4868 still and 0.00452 stirred. Disabling activation leaves both at 0.4868. First-order rates are declared assumptions, not calibrated real dissolution measurements.
- Titration: two prepared sample amounts reach the modeled persistent faint-pink endpoint after 6 and 9 metered drops (0.72 and 1.08 mL). Disabling delivery produces no drops or endpoints. Indicator and normalized neutralization are analytical assumptions.

All four use MuJoCo position actuators and deterministic policies. Engagement is geometric, not force-contact-qualified manipulation; fluid dynamics and physical chemistry are not solved. No learned-policy quality, sim-to-real transfer, physical readiness, or student learning improvement is established. The physical pH demo scope is unchanged.

The integrated existing and new simulation suites passed 57 tests. Final MP4 metadata, source hashes and video hashes are recorded in [VIDEOS.json](../../simulation/lab_demos/VIDEOS.json). All final videos are 1280×720, with playback speed identified in captions. Positive and action-disabled evidence are kept separately. Later caption/lighting changes preserve the same numerical policy outcomes.
