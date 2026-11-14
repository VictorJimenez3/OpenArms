# Wet-lab bring-up and training

> **Application boundary:** the app uses mock or MuJoCo execution with physical actuation disabled. The selected two-vessel Smartivity direction is defined in [PROJECT](PROJECT.md); [the architecture checklist](ARCHITECTURE.md#kit-scope-and-bench-handoff) records the outstanding physical handoff. This runbook retains supervised hardware procedures and historical baseline evidence; none of these commands is dispatched by the student app. Normal successful return to the taught HOME may be automatic. Replenishing materials and recovery after faults are separate readiness checks.

Start with one fixed-fixture water pour. Reuse the same robot calibration, leader/follower link, and saved-pose executor that moved the mandarin. The only geometry to teach is the cup, receiver, and clear travel path on the actual bench. Use the planned fixed webcam views for evidence: one wide view of the arm and fixtures, one close view of the stream and receiver. Camera calibration can follow after the first pour.

## Current qualification and apparatus

**Unverified:** physical two-vessel fit, dry/water pour, camera registration, selected chemistry, repeated reset and first-minute student action. The successful historical mandarin transfer proves none of these. Victor and Duc's physical bring-up continues independently of Joseph's simulation/camera/integration work.

Use exactly two active vessels: donor A and stationary receiver C. The [photo-derived vessel models](../simulation/models/vessels/measured_2026_11_14/README.md) estimate donor height/rim/base near 51/41/31 mm and receiver near 32/78/59 mm; actual measurements and fit remain required. The receiver's underside `100ml.` mark is a nominal capacity label, not a visible fill line or verified maximum capacity. The existing two-vessel base-plate lane owns CAD and marker geometry. Its `5c6ee1f` digital candidate has a 170×156 mm plate, fit gauges and ArUco 20–23 patterns at 27 mm with a manifest; independent review/integration and all physical checks remain pending. The older four-slot export is not the final apparatus. Do not delay a secured working pour for elaborate CAD.

The shared Notion physical page records review of the kit's Magic Potion 1 manual pages 30–31. Manual review does not qualify the robotic two-vessel adaptation, actual packet inventory, preparation or outcome. Use water for almost all calibration and preserve reagents for a few chemistry checks, rehearsals and retries. Food color can test visibility; it is not the final science result.

Keep a handoff with measured vessel/fixture geometry and uncertainty, setup/pose/calibration versions, camera IDs and mounts, taught trajectory, water receipts including failures/spills, actual chemistry observations and reset readiness. Fiducial IDs/dimensions/placement and fixture-to-robot registration need their own evidence; recessed letters and rulers are not fiducials.

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

**Exit criterion:** A student uses voice or text to request a supported action, confirms the exact plan, and receives an independent observation. A visible physical action in the first minute is the timing target; measure it rather than claiming it from software tests. Prediction/reflection are optional. The operator can stop the arm independently.

- Optionally offer two prepared conditions only after the primary one-result workflow is reliable. This is not a first-minute judging gate. A human can load the chosen cup at the same A fixture; keep the motion constant and record the loaded condition.
- Route the confirmed request to a versioned `add_sample` skill with a fixed receiver and one portion. Expose one working route first. The current browser/iPhone app uses the shared session service, with physical dispatch disabled. The historical mandarin relay is not its backend. Until the water skill is registered and rehearsed through the current app, use the supervised local runner and describe that setup accurately.
- Record what the student can actually observe. For water delivery, use receiver fill or a tared scale and report measured mass when available. For chemistry, verify the preferred magic-tea/citric-acid preparation and visible response; use a small contained citric-acid/baking-soda reaction only as the selected fallback after its own check. Earlier buoyancy, grape-juice and food-color proposals are historical alternatives, not the selected physical demonstration.
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

The November 14 physical result, exact `bench-a.json` snapshot, original `poses.json` baseline, raw stage outputs, teaching trace and before/carry/after images are in the [committed mandarin evidence bundle](../research/joseph/mandarin-transfer-2026-11-14/README.md). The final run physically picked up the mandarin and placed it on the red card.

For the fruit bench, the supervised C→B run used a +5° pickup swivel, higher carry, and the original B release. The new runner option can preview or rehearse that path with `openarms transfer C --bench --offset 5 --high-carry --dry`. Use `--preview` for an offline inspection. A loaded run pauses for visible lift confirmation. The staged physical trial succeeded, and the packaged path has software tests. The packaged path needs its own supervised bench run.
