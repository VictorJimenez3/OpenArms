"""Read portable camera episodes and align them with existing teleop JSONL traces.

No robot drivers or optional image packages are imported here. Timestamps describe
host receipt time, not exposure time or hardware synchronization.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
from pathlib import Path
import re
import statistics


def finite(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def asset_path(root: Path, value: str) -> Path:
    """An episode may only reference assets contained in its own directory."""
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("asset paths must be nonempty relative paths")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"asset escapes episode directory: {value}")
    return path


def read_jsonl(path: Path, *, timestamps: bool = True) -> list[dict]:
    rows, previous = [], -math.inf
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: expected object")
        if timestamps:
            stamp = finite(row.get("t"), "t")
            if stamp < previous:
                raise ValueError(f"{path.name}:{line_number}: timestamps go backwards")
            previous = stamp
        rows.append(row)
    return rows


def _clock_offset(stream: dict, domain: str) -> tuple[float, float]:
    clock = stream.get("clock_domain")
    if not isinstance(clock, str) or not clock:
        raise ValueError("every stream requires a clock_domain")
    if clock != domain and ("offset_s" not in stream or "offset_uncertainty_s" not in stream):
        raise ValueError("different clocks require measured offset_s and offset_uncertainty_s")
    offset = finite(stream.get("offset_s", 0), "offset_s")
    uncertainty = finite(stream.get("offset_uncertainty_s", 0), "offset_uncertainty_s")
    if uncertainty < 0:
        raise ValueError("offset uncertainty cannot be negative")
    return offset, uncertainty


def load_episode(path: str | Path) -> dict:
    path = Path(path)
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported episode schema_version")
    if manifest.get("telemetry_complete") is False:
        raise ValueError("telemetry is not finalized; stop recorder then attach its trace")
    if not isinstance(manifest.get("episode_id"), str) or not manifest["episode_id"]:
        raise ValueError("episode_id is required")
    if manifest.get("provenance") not in {"synthetic", "recorded", "physical", "simulated"}:
        raise ValueError("explicit episode provenance is required")
    clock = manifest.get("clock", {})
    if clock.get("units") != "seconds" or not clock.get("domain"):
        raise ValueError("episode clock requires domain and seconds units")
    if clock.get("hardware_synchronized") is not False:
        raise ValueError("this capture format does not establish hardware synchronization")
    telemetry = manifest.get("telemetry", {})
    trace_offset, trace_uncertainty = _clock_offset(telemetry, clock["domain"])
    trace = read_jsonl(asset_path(path.parent, telemetry.get("path")))
    if not trace:
        raise ValueError("telemetry is empty")
    for row in trace:
        if row.get("event") not in {"sample", "checkpoint"}:
            raise ValueError("telemetry event must be sample or checkpoint")
        if row["event"] == "checkpoint" and not isinstance(row.get("name"), str):
            raise ValueError("checkpoint requires name")
        row["aligned_t"] = row["t"] + trace_offset
    cameras, ids = [], set()
    if not isinstance(manifest.get("cameras"), list) or len(manifest["cameras"]) != 2:
        raise ValueError("a bench episode requires exactly two camera descriptors")
    for descriptor in manifest["cameras"]:
        camera_id = descriptor.get("camera_id")
        if not isinstance(camera_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", camera_id) or camera_id in ids:
            raise ValueError("camera_id must be filename-safe and unique")
        ids.add(camera_id)
        offset, uncertainty = _clock_offset(descriptor, clock["domain"])
        fps = finite(descriptor.get("fps_nominal"), "fps_nominal")
        if fps <= 0:
            raise ValueError("fps_nominal must be positive")
        sidecar = asset_path(path.parent, descriptor.get("frames"))
        video = asset_path(path.parent, descriptor.get("video"))
        rows = read_jsonl(sidecar) if sidecar.exists() else []
        expected_index = 0
        for row in rows:
            if row.get("status") not in {"ok", "dropped"}:
                raise ValueError("frame status must be ok or dropped")
            if row["status"] == "ok":
                if type(row.get("frame_index")) is not int or row.get("frame_index") != expected_index:
                    raise ValueError("successful frame indexes must be contiguous from zero")
                expected_index += 1
            elif row.get("frame_index") is not None:
                raise ValueError("dropped frames cannot have a video frame index")
            if finite(row.get("read_duration_s", 0), "read_duration_s") < 0:
                raise ValueError("read duration cannot be negative")
            row["aligned_t"] = row["t"] + offset
        cameras.append({**descriptor, "rows": rows, "video_path": video,
                        "sidecar_missing": not sidecar.exists(), "video_missing": not video.exists(),
                        "clock_uncertainty_s": uncertainty + trace_uncertainty})
    return {"manifest": manifest, "root": path.parent.resolve(), "trace": trace, "cameras": cameras}


def nearest_frame(camera: dict, t: float, max_skew_s: float = 0.1) -> dict:
    t = finite(t, "query timestamp")
    max_skew_s = finite(max_skew_s, "max_skew_s")
    if max_skew_s < 0:
        raise ValueError("max_skew_s must be nonnegative")
    result = {"camera_id": camera["camera_id"], "status": "missing", "frame_index": None,
              "t": None, "skew_s": None, "clock_uncertainty_s": camera["clock_uncertainty_s"]}
    if camera["video_missing"] or camera["sidecar_missing"]:
        return result
    valid = [r for r in camera["rows"] if r["status"] == "ok"]
    if not valid:
        return result
    stamps = [r["aligned_t"] for r in valid]
    index = bisect.bisect_left(stamps, t)
    choices = valid[max(0, index - 1):min(len(valid), index + 1)]
    row = min(choices, key=lambda x: abs(x["aligned_t"] - t))
    skew = row["aligned_t"] - t
    status = "ok" if abs(skew) + camera["clock_uncertainty_s"] <= max_skew_s else "stale"
    return {**result, "status": status, "frame_index": row["frame_index"], "t": row["aligned_t"], "skew_s": skew}


def align_episode(path: str | Path, max_skew_s: float = 0.1) -> dict:
    episode = load_episode(path)
    finite(max_skew_s, "max_skew_s")
    if max_skew_s < 0:
        raise ValueError("max_skew_s must be nonnegative")
    report = {"schema_version": 1, "episode_id": episode["manifest"]["episode_id"],
              "provenance": episode["manifest"]["provenance"], "hardware_synchronized": False,
              "timestamp_semantics": "host receipt; exposure latency unknown", "max_skew_s": max_skew_s,
              "telemetry_rows": len(episode["trace"]), "cameras": [], "paired_frames": []}
    for camera in episode["cameras"]:
        valid = [r for r in camera["rows"] if r["status"] == "ok"]
        gaps = [b["aligned_t"] - a["aligned_t"] for a, b in zip(valid, valid[1:])]
        matches = [nearest_frame(camera, r["aligned_t"], max_skew_s) for r in episode["trace"]]
        skews = [abs(r["skew_s"]) for r in matches if r["skew_s"] is not None]
        report["cameras"].append({"camera_id": camera["camera_id"], "frames_ok": len(valid),
            "dropped_reads": sum(r["status"] == "dropped" for r in camera["rows"]),
            "estimated_missing_intervals": sum(max(0, round(g * camera["fps_nominal"]) - 1) for g in gaps),
            "max_gap_s": max(gaps, default=None), "sidecar_missing": camera["sidecar_missing"],
            "video_missing": camera["video_missing"], "aligned_rows": sum(r["status"] == "ok" for r in matches),
            "stale_rows": sum(r["status"] == "stale" for r in matches),
            "missing_rows": sum(r["status"] == "missing" for r in matches),
            "median_abs_skew_s": statistics.median(skews) if skews else None,
            "max_abs_skew_s": max(skews, default=None), "clock_uncertainty_s": camera["clock_uncertainty_s"],
            "max_read_duration_s": max((r.get("read_duration_s", 0) for r in camera["rows"]), default=None),
            "exposure_latency_s": None})
    for row in episode["trace"]:
        views = [nearest_frame(c, row["aligned_t"], max_skew_s) for c in episode["cameras"]]
        report["paired_frames"].append({"t": row["aligned_t"], "event": row["event"], "name": row.get("name"),
            "views": views, "intercamera_skew_s": abs(views[0]["t"] - views[1]["t"])
            if all(v["t"] is not None for v in views) else None})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--max-skew-s", type=float, default=0.1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = align_episode(args.episode, args.max_skew_s)
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
