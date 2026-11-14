"""Camera-only sidecars, file replay, and an explicitly synthetic two-view fixture.

Live capture is opt-in and never imports or starts an arm recorder/executor.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import re
import threading
import time
import uuid

from .episode import finite, read_jsonl


def image_dependencies():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Image operations need isolated-environment opencv-python-headless and numpy") from exc
    return cv2, np


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows))


def _camera_config(cameras):
    if len(cameras) != 2:
        raise ValueError("provide exactly two cameras")
    ids, devices = set(), set()
    for camera in cameras:
        camera_id = camera.get("camera_id", "")
        if not isinstance(camera_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", camera_id) or camera_id in ids:
            raise ValueError("camera_id must be a unique filename-safe stable identity")
        ids.add(camera_id)
        device = camera.get("device")
        if isinstance(device, bool) or not isinstance(device, (int, str)) or device == "" or str(device) in devices:
            raise ValueError("each camera requires a distinct device selector")
        devices.add(str(device))
        if not camera.get("identity_verified"):
            raise ValueError("verify each device selector against its stable camera_id before capture")
        fps = finite(camera.get("fps_nominal", 15), "fps_nominal")
        if fps <= 0 or fps > 240:
            raise ValueError("fps_nominal must be in (0, 240]")


def capture_camera(source, out: Path, descriptor: dict, *, duration_s: float,
                   clock=time.monotonic, sleep=time.sleep, writer_factory=None) -> dict:
    """Record a read()-compatible frame source. Fake sources exercise this offline.

    Missing reads are written to the sidecar and do not consume video indices.
    Writer timestamps are deliberately not used for alignment.
    """
    duration_s = finite(duration_s, "duration_s")
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    cv2, _ = image_dependencies()
    fps = finite(descriptor["fps_nominal"], "fps_nominal")
    if fps <= 0:
        raise ValueError("fps_nominal must be positive")
    started, frame_index, writer, error = clock(), 0, None, None
    shape = None
    sidecar = out / descriptor["frames"]
    try:
        with sidecar.open("x") as log:
            while clock() - started < duration_s:
                before = clock()
                ok, frame = source.read()
                stamp = clock()
                ok = bool(ok and frame is not None)
                if ok:
                    current_shape = tuple(frame.shape[:2])
                    if shape is not None and shape != current_shape:
                        raise ValueError("camera frame dimensions changed mid-episode")
                    shape = current_shape
                    if writer is None:
                        writer = (writer_factory or cv2.VideoWriter)(
                            str(out / descriptor["video"]), cv2.VideoWriter_fourcc(*"MJPG"),
                            fps, (frame.shape[1], frame.shape[0]))
                        if not writer.isOpened():
                            raise RuntimeError("could not open video writer")
                    writer.write(frame)
                row = {"frame_index": frame_index if ok else None, "t": stamp,
                       "status": "ok" if ok else "dropped", "read_duration_s": max(0, stamp - before)}
                log.write(json.dumps(row, allow_nan=False) + "\n")
                log.flush()
                frame_index += int(ok)
                sleep(max(0, 1 / fps - (clock() - before)))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        source.release()
        if writer is not None:
            writer.release()
    return {"camera_id": descriptor["camera_id"], "frames_written": frame_index, "error": error}


def capture_live(cameras: list[dict], out: str | Path, *, duration_s=60,
                 episode_id=None, request_id=None, plan_id=None) -> Path:
    """Explicitly requested camera access only; call separately from robot tools."""
    _camera_config(cameras)
    duration_s = finite(duration_s, "duration_s")
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    cv2, _ = image_dependencies()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    host_id = platform.node()
    descriptors, sources, threads, receipts = [], [], [], []
    manifest = {"schema_version": 1, "episode_id": episode_id or str(uuid.uuid4()),
                "request_id": request_id, "plan_id": plan_id, "provenance": "physical",
                "clock": {"domain": "host-monotonic", "host_id": host_id, "units": "seconds",
                          "hardware_synchronized": False, "timestamp_semantics": "host receipt after read"},
                "telemetry": {"path": "joint_trace.jsonl", "clock_domain": "unverified"},
                "cameras": descriptors, "capture_complete": False, "telemetry_complete": False}
    try:
        for camera in cameras:
            camera_id = camera["camera_id"]
            descriptor = {"camera_id": camera_id, "role": camera.get("role", camera_id),
                          "video": f"{camera_id}.avi", "frames": f"{camera_id}.frames.jsonl",
                          "clock_domain": "host-monotonic", "offset_s": 0, "offset_uncertainty_s": 0,
                          "calibration_id": camera.get("calibration_id"), "fps_nominal": camera.get("fps_nominal", 15),
                          "device_selector": camera["device"], "identity_verified": True}
            descriptors.append(descriptor)
            source = cv2.VideoCapture(camera["device"])
            sources.append(source)
            if not source.isOpened():
                raise RuntimeError(f"camera could not be opened: {camera_id}")
            source.set(cv2.CAP_PROP_FPS, descriptor["fps_nominal"])
        write_json(out / "episode.json", manifest)
        for source, descriptor in zip(sources, descriptors):
            thread = threading.Thread(target=lambda s=source, d=descriptor: receipts.append(
                capture_camera(s, out, d, duration_s=duration_s)), daemon=False)
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        manifest["capture_complete"] = all(r["error"] is None for r in receipts)
        manifest["camera_receipts"] = receipts
        write_json(out / "episode.json", manifest)
        return out / "episode.json"
    finally:
        for thread in threads:
            thread.join()
        for source in sources:
            source.release()
        if not (out / "episode.json").exists():
            write_json(out / "episode.json", manifest)


def finalize_episode(episode_path: str | Path, trace_path: str | Path, *, recorder_finished: bool = False,
                     same_host_clock: bool = False, clock_domain: str | None = None,
                     offset_s: float | None = None, offset_uncertainty_s: float | None = None) -> Path:
    """Attach an immutable trace after the operator confirms the recorder exited.

    The existing recorder buffers its JSONL output. Copying during its run could
    silently lose the final checkpoints, so capture and finalization are separate.
    A same-host assertion also means the same boot/session, not a later reboot.
    """
    if not recorder_finished:
        raise ValueError("confirm recorder has exited before finalizing telemetry")
    if same_host_clock and clock_domain is not None:
        raise ValueError("choose same-host clock or explicit external clock mapping")
    path = Path(episode_path)
    manifest = json.loads(path.read_text())
    if manifest.get("telemetry_complete"):
        raise ValueError("telemetry is already finalized; create a new episode instead")
    if same_host_clock:
        telemetry = {"path": "joint_trace.jsonl", "clock_domain": manifest["clock"]["domain"],
                     "offset_s": 0, "offset_uncertainty_s": 0, "same_host_asserted_by_operator": True}
    else:
        if not clock_domain or offset_s is None or offset_uncertainty_s is None:
            raise ValueError("assert same host/boot or supply measured clock mapping and uncertainty")
        offset_s = finite(offset_s, "offset_s")
        offset_uncertainty_s = finite(offset_uncertainty_s, "offset_uncertainty_s")
        if offset_uncertainty_s < 0:
            raise ValueError("offset uncertainty cannot be negative")
        telemetry = {"path": "joint_trace.jsonl", "clock_domain": clock_domain,
                     "offset_s": offset_s, "offset_uncertainty_s": offset_uncertainty_s,
                     "same_host_asserted_by_operator": False}
    source = Path(trace_path)
    before = source.stat()
    rows = read_jsonl(source)
    if not rows or not any(row.get("event") == "sample" for row in rows):
        raise ValueError("telemetry contains no samples")
    raw = source.read_bytes()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("telemetry changed during finalization; stop recorder first")
    with (path.parent / "joint_trace.jsonl").open("xb") as destination:
        destination.write(raw)
    manifest["telemetry"] = {**telemetry, "recorder_finished_asserted_by_operator": True,
                             "finish_checkpoint_present": any(r.get("event") == "checkpoint" and r.get("name") == "finish" for r in rows)}
    manifest["telemetry_complete"] = True
    write_json(path, manifest)
    return path


def make_fixture(out: str | Path) -> Path:
    """Create two encoded videos, telemetry, checkpoints and annotations. No hardware."""
    cv2, np = image_dependencies()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    fps, count, base = 10, 81, 1000.0
    joints = ("shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos")
    checkpoint_schedule = {0: "HOME", 5: "open", 15: "ABOVE_A", 25: "GRASP_A", 30: "cup",
                           45: "ABOVE_C", 55: "TIP_C", 80: "finish"}
    trace, poses, truth = [], {"poses": {}, "gripper": {}}, []
    for index in range(count):
        t = base + index / fps
        grip = 70.0 if index < 30 or index >= 70 else 20.0
        state = {joint: round(15 * math.sin(index / 15 + j), 5) for j, joint in enumerate(joints)}
        state["gripper.pos"] = grip
        if index == 80:
            state = {**poses["poses"]["HOME"], "gripper.pos": grip}
        trace.append({"t": t, "event": "sample", "leader": state, "command": state, "sent": state, "state": state})
        if index in checkpoint_schedule:
            name = checkpoint_schedule[index]
            trace.append({"t": t, "event": "checkpoint", "name": name, "state": state, "command": state})
            if name in {"open", "cup"}:
                poses["gripper"][name] = grip
            elif name != "finish":
                poses["poses"][name] = {joint: state[joint] for joint in joints}
    write_jsonl(out / "joint_trace.jsonl", trace)
    write_json(out / "poses.json", poses)
    cameras = []
    for view, delay in (("overview", 0.012), ("side", 0.027)):
        descriptor = {"camera_id": f"fixture-{view}", "role": view, "video": f"{view}.avi",
                      "frames": f"{view}.frames.jsonl", "clock_domain": "synthetic-clock", "offset_s": 0,
                      "offset_uncertainty_s": 0, "calibration_id": None, "fps_nominal": fps}
        writer = cv2.VideoWriter(str(out / descriptor["video"]), cv2.VideoWriter_fourcc(*"MJPG"), fps, (480, 320))
        if not writer.isOpened():
            raise RuntimeError("fixture video encoder unavailable")
        frames, video_index = [], 0
        try:
            for index in range(count):
                stamp = base + index / fps + delay
                dropped = view == "side" and index in {39, 40, 41}
                frames.append({"frame_index": None if dropped else video_index, "t": stamp,
                               "status": "dropped" if dropped else "ok", "read_duration_s": 0.003})
                if dropped:
                    continue
                frame = np.full((320, 480, 3), (44, 35, 28), dtype=np.uint8)
                x = int(100 + max(0, min(1, (index - 30) / 15)) * 230) if index < 60 else int(330 - min(1, (index - 60) / 15) * 230)
                y = 175 if view == "overview" else int(190 - (65 if 30 <= index < 70 else 0))
                cv2.rectangle(frame, (305, 200), (385, 270), (100, 170, 180), 3)
                cv2.rectangle(frame, (x - 22, y - 30), (x + 22, y + 30), (20, 185, 245), -1)
                cv2.putText(frame, "SYNTHETIC SOFTWARE FIXTURE", (15, 24), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
                cv2.putText(frame, f"{view} t={stamp:.3f}", (15, 48), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
                writer.write(frame)
                truth.append({"camera_id": descriptor["camera_id"], "frame_index": video_index, "t": stamp,
                              "object_id": "source-cup", "box_xyxy": [x-22, y-30, x+22, y+30],
                              "feature": "synthetic rectangle center", "pixel_point": [x, y], "provenance": "synthetic"})
                video_index += 1
        finally:
            writer.release()
        write_jsonl(out / descriptor["frames"], frames)
        cameras.append(descriptor)
    write_jsonl(out / "annotations.jsonl", truth)
    manifest = {"schema_version": 1, "episode_id": "synthetic-cup-demo-v1", "provenance": "synthetic",
                "clock": {"domain": "synthetic-clock", "host_id": "fixture", "units": "seconds", "hardware_synchronized": False},
                "telemetry": {"path": "joint_trace.jsonl", "clock_domain": "synthetic-clock", "offset_s": 0, "offset_uncertainty_s": 0},
                "cameras": cameras, "poses": "poses.json", "annotations": "annotations.jsonl",
                "capture_complete": True, "telemetry_complete": True,
                "limitations": ["Generated drawings and joints; no robot or cup result", "Side view has three deliberate dropped reads"]}
    write_json(out / "episode.json", manifest)
    return out / "episode.json"


def replay_frame(episode_path: str | Path, camera_id: str, frame_index: int):
    from .episode import load_episode
    cv2, _ = image_dependencies()
    if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
        raise ValueError("frame_index must be a nonnegative integer")
    episode = load_episode(episode_path)
    camera = next((c for c in episode["cameras"] if c["camera_id"] == camera_id), None)
    if camera is None:
        raise ValueError("unknown camera_id")
    source = cv2.VideoCapture(str(camera["video_path"]))
    try:
        source.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = source.read()
        if not ok:
            raise ValueError("video frame is missing or cannot be decoded")
        return frame
    finally:
        source.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fixture = sub.add_parser("fixture", help="generate an explicitly synthetic offline fixture")
    fixture.add_argument("--out", type=Path, required=True)
    live = sub.add_parser("live", help="camera-only capture; never starts the robot recorder")
    live.add_argument("--devices", type=Path, required=True, help="JSON list of two verified camera identities")
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--duration-s", type=float, default=60)
    live.add_argument("--request-id")
    live.add_argument("--plan-id")
    finalize = sub.add_parser("finalize", help="attach trace only AFTER the recorder exited and flushed it")
    finalize.add_argument("episode", type=Path)
    finalize.add_argument("--trace", type=Path, required=True)
    finalize.add_argument("--recorder-finished", action="store_true", required=True)
    finalize.add_argument("--same-host-clock", action="store_true")
    finalize.add_argument("--clock-domain")
    finalize.add_argument("--offset-s", type=float)
    finalize.add_argument("--offset-uncertainty-s", type=float)
    replay = sub.add_parser("replay-frame")
    replay.add_argument("episode", type=Path)
    replay.add_argument("--camera-id", required=True)
    replay.add_argument("--frame-index", type=int, required=True)
    replay.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "fixture":
        print(make_fixture(args.out))
    elif args.command == "live":
        print(capture_live(json.loads(args.devices.read_text()), args.out,
                           duration_s=args.duration_s, request_id=args.request_id, plan_id=args.plan_id))
    elif args.command == "finalize":
        print(finalize_episode(args.episode, args.trace, recorder_finished=args.recorder_finished,
                               same_host_clock=args.same_host_clock, clock_domain=args.clock_domain,
                               offset_s=args.offset_s, offset_uncertainty_s=args.offset_uncertainty_s))
    else:
        cv2, _ = image_dependencies()
        if not cv2.imwrite(str(args.out), replay_frame(args.episode, args.camera_id, args.frame_index)):
            raise RuntimeError("failed to write replay image")


if __name__ == "__main__":
    main()
