# Wet-lab bring-up and training

Start with one fixed-fixture water pour. Reuse the same robot calibration, leader/follower link, and saved-pose executor that moved the mandarin. The only geometry to teach is the cup, receiver, and clear travel path on the actual bench. Use the planned fixed webcam views for evidence: one wide view of the arm and fixtures, one close view of the stream and receiver. Camera calibration can follow after the first pour.

## Minimum working demo

**Exit criterion:** The robot picks up one plastic source cup, pours a pre-portioned amount of water into a fixed plastic receiver, returns the cup, and parks at HOME. An observer and before/after views confirm where the water went and whether it spilled.

1. **Before equipment arrives.** Keep the calibrated laptop/arms ready and run the offline checks below. Prepare a catch tray, stable cup holder, wide-mouth clear plastic receiver, and a way to mark both fixture positions. Use water for bring-up. Keep the controllers, power supplies, and connectors out of the tray and splash path.
2. **Mount once.** Secure the arm and arrange A as the source and C as the receiver. Place both inside the tray. Pick one cup shape and leave the fixtures and camera mounts fixed while reusing a take.
3. **Teach one empty-cup take.** Run `openarms capture water`. Move the leader from a comfortable starting pose. Press Enter at the prompts for HOME, open, above source, around source, grip, upright above receiver, tip, and return. If the last stop is just outside HOME, type `keep` to save the take, then restore the saved HOME before replay. The take includes a checkpoint file and a continuous joint trace.
4. **Run dry.** With the same empty cup in A, run `openarms pour dry`. Confirm the start, verify the cup is lifted at the pause, and watch the cup lip, receiver rim, and return clearance. If anything catches, stop and fix the affected checkpoint or fixture. Keep the power cutoff accessible and the work area clear.
5. **Run one portion.** Reset the cup in its holder and add one small pre-measured portion of water. Run `openarms pour water`. Capture both views and log actual delivery, spills, cup return, and HOME. A completed command reports motion, while the observation records what happened. Repeat the same setup before relying on it for a demo.

```sh
export PATH="$PWD/firmware:$PATH"
openarms status
openarms capture water
openarms pour preview
openarms pour dry
openarms pour water
```

The pour command is local and supervised. It validates every required waypoint against the follower's calibration, checks the actual start pose, asks for a lift observation, and executes the existing `add_sample(A, C, 1)` expansion. The receiver is C in the wet-lab plan. C in the mandarin trial was a pickup position. Use separate pose files for the two benches.

The bench Mac already has a working environment. A clean checkout can reuse an existing Python 3.12 LeRobot environment by setting `OPENARMS_PYTHON` to its Python executable. Otherwise set up `.venv` and install the [pinned LeRobot driver](../firmware/README.md). With that environment active, run `python -m firmware.openarms_executor.check_pose_arm` before equipment arrives.

## Real demo

**Exit criterion:** A student uses voice or text to choose a prepared condition, states a prediction, confirms the plan, and sees one actual observation and a follow-up question. The operator can stop the arm independently.

- Give the student two prepared conditions once the first route repeats. A human can load the chosen cup at the same A fixture for either condition. Keep the motion constant and record which prepared condition was loaded.
- Route the confirmed request to a versioned `add_sample` skill with a fixed receiver and one portion. Expose one working route first. The current phone relay is mandarin-specific. Until water requests are wired and rehearsed, use the local terminal runner with a human operator and describe that setup accurately.
- Record what the student can actually observe. For water delivery, use receiver fill or a tared scale and report measured mass when available. For a science comparison, the lab team should choose the approved materials and reference observations. A prepared buoyancy release is a fallback if the carried-cup pour is unreliable. [Experiment options and validation](../research/victor/laboratory-experiments-and-feasibility.md)
- Rehearse the complete interaction and reset twice on the final setup. Log outcome, elapsed time, interventions, and any spill. Keep a successful take and the receipts available for the demo.

## Stretch demo

**Exit criterion:** The agent produces a versioned candidate from human demonstrations, compares it with the baseline offline, and the operator observes a successful supervised bench trial. A held-out fixture or source position is a separate test.

1. Collect several quick demonstrations with the fixtures and calibration fixed. Use `openarms capture water --take 02`, then `03`, and so on. Hold at each boundary. The named checkpoints identify the pickup and return, upright receiver approach, tip, and recovery. Retain the continuous traces for later phase segmentation and imitation learning.
2. In a second terminal, run `openarms compare-pours --watch` while you collect takes. Each change to the take set triggers an offline batch. For a one-off comparison, pass the capture files explicitly. The harness evaluates all pickup/receiver pairs on a fake arm, keeps same-take baselines, and shortlists three completed cross-take candidates with the smallest maximum joint change across the transit. Camera occlusion, collisions, grip, and liquid behavior still need physical checks.
3. For each candidate, save the proposed pose file under a new name, run `openarms pour preview --poses PATH`, and inspect both joins through `ABOVE_A` and `ABOVE_C`. A pickup phase and the cup return stay paired. Bench-test one empty-cup candidate, then one water trial after approval. Keep the last working version available.
4. Have the agent compare bench receipts against the retained baseline. Measure clearance, pickup and delivery success, interventions, duration, and reset. Record the baseline, data used, candidate, metric and disposition on each pass. The watcher runs while its terminal is open. Automatic trace segmentation, receipt-driven proposals, and promotion based on physical trials are follow-up work.
5. If time remains, use the fixed cameras to localize a shifted source while the arm is parked. Fit the camera-to-bench mapping, check an unloaded approach, and try one held-out placement. An imitation policy is a separate experiment with a repeated, fixed task and a held-out evaluation set. Keep it outside the minimum path.

## Recovery and evidence

Controller status and physical observations are separate. After a failed lift or stop, retain the current grip, inspect the bench, and recover under operator control. Avoid repeating a wet movement until the cup, receiver, and source quantity are known.

For the fruit bench, the supervised C→B run used a +5° pickup swivel, higher carry, and the original B release. The new runner option can preview or rehearse that path with `openarms transfer C --bench --offset 5 --high-carry --dry`. Use `--preview` for an offline inspection. A loaded run pauses for visible lift confirmation. The staged physical trial succeeded, and the packaged path has software tests. The packaged path needs its own supervised bench run.
