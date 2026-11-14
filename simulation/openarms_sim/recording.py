"""Plays a motion recorded on the real arm, and builds the bench from it.

Record one move with `lerobot-record` (pick the object up at A, put it down at
B), then:

    python -m openarms_sim.recording recordings/block_A_B
    mjpython -m openarms_sim.recording recordings/block_A_B --view

No measuring is needed. The moment the gripper closes on the object marks
point A, and the moment it lets go marks point B; the simulation draws the
object and the two marks there. The real arm repeats the same file with
`lerobot-replay`.

Because the motion really happened, anything the simulation shows going wrong
(the gripper under the table, a pick and a place at different heights) is a
sign that config/joint_map.yaml is off, not that the motion is unsafe. Those
are reported under `mismatches`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np

from .chemistry import load_model
from .config import ARM_JOINTS, OUTPUT_DIR, Bench, ObjectSpec, Station, load_chemistry_config, load_joint_map
from .joints import JointMap
from .motion import Segment
from .player import Player
from .render import VideoRecorder, camera
from .scene import build_scene

HOLD_GAP = 8.0  # gripper units: how far the follower's jaw stays open of the command while it holds something
VIDEO_SPEED = 2.0
GEOMETRY_CODES = {"hits_table", "hits_object", "held_hits_table", "held_hits_object", "self_collision", "bad_release"}


@dataclass
class Recording:
    path: Path
    fps: int
    task: str
    state: np.ndarray  # what the follower arm actually did: N x 6, degrees and gripper 0..100
    action: np.ndarray  # what the leader arm commanded: N x 6

    @property
    def seconds(self) -> float:
        return len(self.state) / self.fps


def load_recording(path: str | Path, episode: int = 0) -> Recording:
    import pandas as pd  # installed with LeRobot

    path = Path(path)
    info = json.loads((path / "meta" / "info.json").read_text())
    names = info["features"]["observation.state"]["names"]
    expected = [f"{j}.pos" for j in ARM_JOINTS] + ["gripper.pos"]
    if names != expected:
        raise ValueError(f"unexpected joint order in {path}: {names}")
    files = sorted((path / "data").rglob("*.parquet"))
    if not files:
        raise ValueError(f"{path} has no recorded data; the take was probably stopped before it was saved")
    df = pd.concat(pd.read_parquet(f) for f in files)
    df = df[df["episode_index"] == episode].sort_values("frame_index")
    if df.empty:
        raise ValueError(f"{path} has no episode {episode}")
    task = ""
    tasks = path / "meta" / "tasks.parquet"
    if tasks.exists():
        t = pd.read_parquet(tasks)
        task = str(t.index[0]) if len(t) else ""
    return Recording(
        path, int(info["fps"]), task, np.stack(df["observation.state"].to_numpy()), np.stack(df["action"].to_numpy())
    )


def find_hold(rec: Recording) -> tuple[int, int]:
    """Frames where the gripper finished closing on the object and where it let go.

    While the gripper holds something, the object stops the follower's jaw short of
    where the leader commands it, so the follower reads more open than the command.
    The hold is the longest stretch of that."""
    gap = rec.state[:, 5] - rec.action[:, 5]
    holding = gap > HOLD_GAP
    best, start = None, None
    for i, h in enumerate(np.append(holding, False)):
        if h and start is None:
            start = i
        elif not h and start is not None:
            if best is None or i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if best is None or best[1] - best[0] < rec.fps * 0.5:
        raise ValueError(
            "could not find a moment where the gripper was holding something. "
            "Pass --pick-time and --place-time (seconds) to say when it closed and opened."
        )
    close, release = best
    # The jaw is still moving for the first few frames; wait until it has settled.
    g = rec.state[:, 5]
    while close + 1 < release and abs(g[close + 1] - g[close]) > 0.3:
        close += 1
    return close, release - 1


def _fk(scene, jm: JointMap, row: np.ndarray) -> tuple[np.ndarray, float]:
    """Grasp point (metres) and how far the gripper is from level (degrees) for one frame."""
    m, d = scene.model, scene.data
    for name, adr, v in zip(ARM_JOINTS, scene.arm_qadr, row[:5]):
        d.qpos[adr] = jm.to_model(name, float(v))
    mujoco.mj_kinematics(m, d)
    R = d.site_xmat[scene.grasp_site].reshape(3, 3)
    return d.site_xpos[scene.grasp_site].copy(), float(np.degrees(np.arcsin(np.clip(R[2, 0], -1, 1))))


def _empty_bench() -> Bench:
    return Bench((0.70, 0.90), (0.20, 0.0), {}, {}, grasp_height=0.04, lift=0.09)


def bench_from_recording(rec: Recording, jm: JointMap, close: int, release: int, block_size=None) -> tuple[Bench, dict]:
    """Puts mark A where the gripper closed and mark B where it opened."""
    probe = build_scene(_empty_bench())
    pick, pick_pitch = _fk(probe, jm, rec.state[close])
    place, place_pitch = _fk(probe, jm, rec.state[release])
    grasp_height = float(np.clip(pick[2], 0.015, 0.25))
    if block_size:
        width, height = block_size
    else:
        # Not measured: drawn as wide as the closed jaws and a little taller than the grasp.
        jaw = jm.gripper_to_model(float(rec.state[close, 5]))
        width = float(np.clip(0.016 + 0.052 * (jaw - 0.2), 0.012, 0.06))
        height = grasp_height + 0.02
    xs, ys = [pick[0], place[0], 0.0], [pick[1], place[1], 0.0]
    bench = Bench(
        table_size=(max(xs) - min(xs) + 0.40, max(ys) - min(ys) + 0.60),
        table_center=((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2),
        stations={
            "A": Station("A", "point", (float(pick[0]), float(pick[1]))),
            "B": Station("B", "point", (float(place[0]), float(place[1]))),
        },
        objects={"block": ObjectSpec("block", (width, width, height), "A", (0.90, 0.30, 0.15))},
        grasp_height=grasp_height,
        lift=0.09,
        release_tolerance=0.04,  # a real release can be a little high; the object drops onto the mark
    )
    facts = {
        "pick": {"time_s": round(close / rec.fps, 2), "xyz_cm": [round(float(v) * 100, 1) for v in pick]},
        "place": {"time_s": round(release / rec.fps, 2), "xyz_cm": [round(float(v) * 100, 1) for v in place]},
        "gripper_tilt_deg": {"pick": round(pick_pitch, 1), "place": round(place_pitch, 1)},
        "block_drawn_cm": {"width": round(width * 100, 1), "height": round(height * 100, 1), "measured": bool(block_size)},
    }
    return bench, facts


def segments_from_recording(rec: Recording, jm: JointMap, close: int, release: int) -> list[Segment]:
    """One short move per recorded frame, following what the follower arm actually did."""
    q = np.array([jm.pose_to_model(dict(zip(ARM_JOINTS, row[:5]))) for row in rec.state])
    grip = rec.state[:, 5]
    out = []
    for i in range(len(q)):
        j = max(i - 1, 0)
        if i <= close:
            step, index, label = "pick(A)", 0, "reach and grasp"
        elif i <= release:
            step, index, label = "place(B)", 1, "carry and put down"
        else:
            step, index, label = "home()", 2, "return"
        event = "close" if i == close else "open" if i == release else None
        out.append(Segment(index, step, label, q[j], q[i], float(grip[j]), float(grip[i]), 1.0 / rec.fps, event))
    return out


def _consistency(rec: Recording, facts: dict, start_end_gap: float) -> list[str]:
    """Checks that need no ruler: things that must be true if the joint map is right."""
    out = []
    dz = facts["place"]["xyz_cm"][2] - facts["pick"]["xyz_cm"][2]
    if abs(dz) > 1.5:
        out.append(
            f"The object was picked up and put down on the same table, but the simulation puts those "
            f"{abs(dz):.1f} cm apart in height."
        )
    for when in ("pick", "place"):
        if facts[when]["xyz_cm"][2] < 0.5:
            out.append(f"The simulation puts the gripper at or below the table surface at the {when}.")
    if start_end_gap > 15:
        out.append(
            f"The take ends with the arm {start_end_gap:.0f} degrees away from where it started. On replay the "
            "motors switch off at the end, so the arm will drop from there. Re-record and finish at rest."
        )
    return out


def preview_recording(
    path: str | Path,
    render: bool = True,
    block_size: tuple[float, float] | None = None,
    pick_time: float | None = None,
    place_time: float | None = None,
) -> dict:
    """Simulates a recorded move. `block_size` is (width, height) in metres if you know it."""
    rec = load_recording(path)
    jm = JointMap(load_joint_map())
    if pick_time is not None and place_time is not None:
        close, release = round(pick_time * rec.fps), round(place_time * rec.fps)
    else:
        close, release = find_hold(rec)
    bench, facts = bench_from_recording(rec, jm, close, release, block_size)
    scene = build_scene(bench)
    chem_cfg = load_chemistry_config()
    player = Player(scene, jm, chem_cfg, load_model(chem_cfg), strict_limits=False)
    segments = segments_from_recording(rec, jm, close, release)

    video = None
    if render:
        digest = hashlib.sha256(rec.state.tobytes() + json.dumps(jm.cfg, sort_keys=True).encode()).hexdigest()[:12]
        video = OUTPUT_DIR / "recordings" / f"{Path(path).name}-{digest}.mp4"
    recorder = VideoRecorder(scene, video, rec.fps, VIDEO_SPEED, show_blocks=False) if render else None
    player.run(segments, rec.fps, on_frame=recorder)
    if recorder:
        recorder.close()

    gap = float(np.max(np.abs(rec.state[-1, :5] - rec.state[0, :5])))
    mismatches = [i.message for i in player.issues if i.code in GEOMETRY_CODES]
    mismatches += _consistency(rec, facts, gap)
    other = [i for i in player.issues if i.code not in GEOMETRY_CODES]
    at = player.location["block"]
    return {
        "recording": str(path),
        "task": rec.task,
        "seconds": round(rec.seconds, 1),
        "ok": at == "B" and not any(i.severity == "block" for i in other),
        "video_url": video.resolve().as_uri() if video else None,
        "objects": [{"name": "block", "at": at, "started_at": "A", "moved": at != "A"}],
        **facts,
        "joint_map_measured": jm.measured,
        "mismatches": mismatches,
        "warnings": [i.message for i in other],
    }


def view_recording(path: str | Path, block_size=None, seconds: float | None = None) -> None:
    """Loops the recording in the interactive viewer, at real speed."""
    import mujoco.viewer

    rec = load_recording(path)
    jm = JointMap(load_joint_map())
    close, release = find_hold(rec)
    bench, _ = bench_from_recording(rec, jm, close, release, block_size)
    scene = build_scene(bench)
    chem_cfg = load_chemistry_config()
    segments = segments_from_recording(rec, jm, close, release)
    start = time.time()
    with mujoco.viewer.launch_passive(scene.model, scene.data, show_left_ui=False, show_right_ui=False) as viewer:
        cam = camera()
        viewer.cam.lookat[:], viewer.cam.distance = cam.lookat, cam.distance
        viewer.cam.azimuth, viewer.cam.elevation = cam.azimuth, cam.elevation

        def running() -> bool:
            return viewer.is_running() and (seconds is None or time.time() - start < seconds)

        while running():
            player = Player(scene, jm, chem_cfg, load_model(chem_cfg), strict_limits=False)
            next_frame = time.time()

            def on_frame(_p: Player) -> None:
                nonlocal next_frame
                if not running():
                    raise StopIteration
                viewer.sync()
                next_frame += 1.0 / rec.fps
                time.sleep(max(0.0, next_frame - time.time()))

            try:
                player.run(segments, rec.fps, on_frame)
            except StopIteration:
                break


def main() -> None:
    ap = argparse.ArgumentParser(description="Play a motion recorded on the real arm in the simulation.")
    ap.add_argument("path", help="the folder given to lerobot-record as --dataset.root")
    ap.add_argument("--view", action="store_true", help="open the interactive viewer (use mjpython on macOS)")
    ap.add_argument("--block-size", nargs=2, type=float, metavar=("WIDTH_CM", "HEIGHT_CM"), help="if you know it")
    ap.add_argument("--pick-time", type=float, help="seconds into the take when the gripper closed on the object")
    ap.add_argument("--place-time", type=float, help="seconds into the take when it let go")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--seconds", type=float, help="with --view: quit after this long")
    a = ap.parse_args()
    size = (a.block_size[0] / 100, a.block_size[1] / 100) if a.block_size else None
    if a.view:
        view_recording(a.path, size, a.seconds)
        return
    t0 = time.time()
    out = preview_recording(a.path, not a.no_video, size, a.pick_time, a.place_time)
    print(json.dumps(out, indent=2))
    print(f"\ntook {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
