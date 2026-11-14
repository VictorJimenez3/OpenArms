# Two-camera episodes and checkpoint evidence

This camera-only sidecar reuses the existing [`teleop_record.py`](../firmware/openarms_executor/teleop_record.py) JSONL format (`t`, `event`, `state`, `command`, `leader`, `sent`, checkpoint `name`). It does not import that script: importing it would start its argument parser and hardware connection. The motor environment, saved poses and calibration remain untouched. See the existing [wet-lab teaching sequence](../docs/WET_LAB.md) and [research index](../research/README.md).

Run image commands in an isolated Python environment with `numpy` and `opencv-python-headless`; the parent package requirements pin the tested versions. Alignment and event selection require only Python's standard library. All output directories must be new, so an earlier episode cannot be silently overwritten.

## Offline demonstration

From the repository root, with the isolated environment active:

```sh
python -m bench_vision.capture fixture --out outputs/bench-fixture
python -m bench_vision.episode outputs/bench-fixture/episode.json --out outputs/alignment.json
python -m bench_vision.keyframes outputs/bench-fixture/episode.json --out outputs/bench-summary
python -m bench_vision.capture replay-frame outputs/bench-fixture/episode.json \
  --camera-id fixture-overview --frame-index 30 --out outputs/grasp.jpg
python -m pytest -q bench_vision/tests/test_capture.py bench_vision/tests/test_episode.py
```

Open `outputs/bench-summary/index.html`. It includes two views per event, raw selected JPGs, an annotated contact sheet, timestamp skew and a machine-readable phase summary. The synthetic fixture is visibly labeled on every frame. It contains 81 overview frames, 78 side frames, 89 telemetry rows, and three deliberately dropped side reads. It tests software behavior; no actual cup, camera or robot was tested. The fixture and tests are generated locally, with no external data or copied model/code assets.

The event selector uses HOME/open/ABOVE_A/GRASP_A/cup/ABOVE_C/TIP_C/finish checkpoints and infers a release command from the recorded open/cup gripper settings. It handles either gripper polarity. A checkpoint named `lift` is not proof of a successful grip; a release command is not proof the cup released. Missing events are listed, and the outcome remains `unknown` until separate reviewed evidence exists.

## Short supervised capture sequence

Do this only when the bench operator is present. These commands open cameras only and never start robot motion.

1. Mount both cameras and identify each device selector against its permanent label/serial. OpenCV's numeric index is not a stable identity; verify it again after USB reconnect or reboot. Save `devices.json` with the actual verified bindings. Example labels below are placeholders, not an inventory:

   ```json
   [
     {"camera_id":"overview-SERIAL", "role":"overview", "device":0, "identity_verified":true, "fps_nominal":15, "calibration_id":null},
     {"camera_id":"side-SERIAL", "role":"side", "device":1, "identity_verified":true, "fps_nominal":15, "calibration_id":null}
   ]
   ```

2. In the camera terminal, start capture for long enough to finish teaching:

   ```sh
   python -m bench_vision.capture live --devices devices.json \
     --out outputs/cup-take-01 --duration-s 180 --request-id cup-teaching-01
   ```

   In the existing bench terminal, use the already documented supervised `openarms capture water` workflow. Keep the printed trace path. This tooling does not launch it. Both programs must use the same host and boot/session for the shared `time.monotonic()` clock. Camera capture should begin before teaching and finish afterward.

3. After the robot recorder **has exited**, and camera capture has returned, finalize once:

   ```sh
   python -m bench_vision.capture finalize outputs/cup-take-01/episode.json \
     --trace /absolute/path/printed-by-the-recorder.jsonl \
     --recorder-finished --same-host-clock
   python -m bench_vision.keyframes outputs/cup-take-01/episode.json \
     --out outputs/cup-take-01-review
   ```

   The existing recorder buffers its trace. Attaching it before it exits can omit the final samples/checkpoints. Camera capture therefore creates `telemetry_complete:false`; alignment refuses it until explicit finalization. Finalization checks the source did not change while reading and makes an exclusive copy. The flags are operator attestations, not automatic proof that another process stopped. A finalized trace is never overwritten. Partial camera failures remain in `camera_receipts` and `capture_complete:false`; finalizing telemetry does not erase them.

4. Inspect the contact sheet, missing events, missing/stale views, frame gaps and unknown outcome. A clipped recording can be useful diagnostic evidence, but should not qualify a complete skill. The separate skill validator controls that admission decision.

For an external clock, replace `--same-host-clock` with `--clock-domain NAME --offset-s VALUE --offset-uncertainty-s VALUE`. The convention is **episode time = raw stream time + offset**. Use a measured offset and uncertainty. Zero is not a substitute for clock calibration. Do not align monotonic traces across a reboot without an independently measured mapping.

## Format and limitations

`episode.json` schema version 1 identifies two stable cameras, video files, frame JSONL sidecars, source provenance, clock metadata, and the copied joint trace. Paths must be relative and contained within the episode directory, including through symlinks. Camera IDs are filename-safe. Each successful frame has a contiguous zero-based video index, timestamp `t`, `status:"ok"`, and read duration. A failed read has `frame_index:null` and `status:"dropped"`. Video playback FPS is only a convenience: the JSONL timestamps, not encoded frame rate, align the evidence.

`load_episode(path)` validates the manifest and timestamps; `align_episode(path, max_skew_s=.1)` reports nearest frame matches, missing/stale rows, camera-to-telemetry and intercamera skew, dropped reads, estimated missing intervals, largest gap and largest read duration. The estimated missing interval count is a cadence diagnostic, not a count of hardware-dropped exposures. `nearest_frame` includes explicit clock mapping uncertainty in its admission threshold. Read duration is reported separately because it does not bound camera buffering or exposure latency.

`summarize_episode(path, out_dir, max_skew_s=.1)` returns `phases` with aligned `t`, `raw_trace_t`, event provenance and per-camera evidence. It records `clock` and `telemetry_time_offset_s` so consumers can compare against the original trace. A stale frame can appear in the review sheet with a stale label, but must not authorize adaptation. Missing and decode-failed images stay explicit. `outcome.status` starts as `unknown` for all provenance types.

Live timestamps are host receipt times after a blocking OpenCV read, not measured exposure times. Capture threads provide independent camera reads but **do not establish hardware synchronization**. Camera buffering can make an apparently aligned receipt older than expected. The actual devices, driver latency, camera stability, lighting and exposure timestamps still require supervised validation. An OpenCV read can block beyond the requested duration on a failing driver; no hard deadline or realtime capture guarantee is claimed.

The generated AVI/MJPG videos and raw frame replay were exercised offline, including corrupt video, missing files, camera disconnect exceptions, skew, dropped reads, invalid clocks/timestamps, path traversal, duplicate IDs, and immutable finalization. Physical capture remains untested. No motor command, recalibration, or physical experiment is performed by this package.
