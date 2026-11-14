"""Select evidence from recorder checkpoints and gripper events, never video guesses."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from .capture import image_dependencies, write_json
from .episode import align_episode, asset_path, load_episode, nearest_frame


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


CHECKPOINT_PHASES = {"HOME": "before", "open": "open", "ABOVE_A": "approach", "GRASP_A": "pregrasp",
                     "cup": "grasp", "ABOVE_C": "lift", "TIP_C": "tip", "finish": "after",
                     "ABOVE_B": "lift", "GRASP_B": "prerelease"}


def select_events(trace: list[dict]) -> list[dict]:
    """Preserve checkpoint semantics and mark inferred release as unverified.

    A gripper target moving toward the recorded open setting is evidence of a
    release command, not proof that the cup was released. Both gripper polarities
    work because the open and cup checkpoint values define direction.
    """
    if not trace:
        raise ValueError("cannot select events from empty trace")
    events = []
    for row in trace:
        if row.get("event") == "checkpoint":
            events.append({"name": CHECKPOINT_PHASES.get(row["name"], row["name"].lower()),
                           "t": row.get("aligned_t", row["t"]), "event_source": "checkpoint",
                           "raw_trace_t": row["t"],
                           "checkpoint": row["name"], "verified_outcome": False,
                           "annotation": "Operator checkpoint label; physical outcome remains unverified"})
    if not any(e["name"] == "before" for e in events):
        events.append({"name": "before", "t": trace[0].get("aligned_t", trace[0]["t"]),
                       "raw_trace_t": trace[0]["t"],
                       "event_source": "trace_boundary", "checkpoint": None, "verified_outcome": False,
                       "annotation": "First telemetry row; no HOME checkpoint"})
    if not any(e["name"] == "after" for e in events):
        events.append({"name": "after", "t": trace[-1].get("aligned_t", trace[-1]["t"]),
                       "raw_trace_t": trace[-1]["t"],
                       "event_source": "trace_boundary", "checkpoint": None, "verified_outcome": False,
                       "annotation": "Last telemetry row; no finish checkpoint"})
    settings = {}
    for row in trace:
        if row.get("event") == "checkpoint" and row.get("name") in {"open", "cup"}:
            value = row.get("command", row.get("state", {})).get("gripper.pos")
            if isinstance(value, (int, float)):
                settings[row["name"]] = (value, row.get("aligned_t", row["t"]))
    if len(settings) == 2:
        opened, _ = settings["open"]
        closed, closed_t = settings["cup"]
        span = abs(opened - closed)
        if span >= 1:
            was_closed = False
            for row in trace:
                if row.get("event") != "sample" or row.get("aligned_t", row["t"]) < closed_t:
                    continue
                value = row.get("command", row.get("state", {})).get("gripper.pos")
                if not isinstance(value, (int, float)):
                    continue
                if abs(value - closed) < span * .25:
                    was_closed = True
                elif was_closed and abs(value - opened) < span * .25:
                    events.append({"name": "release", "t": row.get("aligned_t", row["t"]),
                                   "raw_trace_t": row["t"],
                                   "event_source": "inferred_gripper", "checkpoint": None,
                                   "verified_outcome": False,
                                   "annotation": "Inferred opening command after grip; cup release needs image/observer review"})
                    break
    events.sort(key=lambda event: event["t"])
    return events


def summarize_episode(episode_path: str | Path, out_dir: str | Path, max_skew_s: float = .1) -> dict:
    episode = load_episode(episode_path)
    alignment = align_episode(episode_path, max_skew_s)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    (out / "frames").mkdir()
    cv2, np = image_dependencies()
    sources = {c["camera_id"]: cv2.VideoCapture(str(c["video_path"]))
               for c in episode["cameras"] if not c["video_missing"]}
    events = select_events(episode["trace"])
    tiles, sections = [], []
    try:
        for index, event in enumerate(events):
            event["views"] = []
            tiles_row, views_html = [], []
            for camera in episode["cameras"]:
                view = nearest_frame(camera, event["t"], max_skew_s)
                view["image"] = None
                view["sha256"] = None
                view["calibration_id"] = camera.get("calibration_id")
                frame = None
                if view["frame_index"] is not None:
                    source = sources.get(camera["camera_id"])
                    if source is not None:
                        source.set(cv2.CAP_PROP_POS_FRAMES, view["frame_index"])
                        ok, frame = source.read()
                        if not ok:
                            frame = None
                            view["status"] = "decode_failed"
                tile = np.full((290, 480, 3), (30, 30, 30), dtype=np.uint8)
                if frame is not None:
                    # Keep raw selected pixels separately from the annotated contact sheet.
                    filename = f"frames/{index:02d}-{camera['camera_id']}.jpg"
                    if not cv2.imwrite(str(out / filename), frame):
                        raise RuntimeError("failed writing selected frame")
                    view["image"] = filename
                    view["sha256"] = file_sha256(out / filename)
                    tile[:240] = cv2.resize(frame, (480, 240))
                label = f"{event['name']} | {camera['camera_id']} | {view['status']}"
                timing = f"event {event['t']:.3f}s"
                if view["skew_s"] is not None:
                    timing += f" | skew {view['skew_s'] * 1000:+.1f}ms"
                cv2.putText(tile, label[:65], (8, 259), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
                cv2.putText(tile, timing, (8, 281), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
                tiles_row.append(tile)
                image_html = f'<img src="{html.escape(view["image"])}" alt="{html.escape(label)}">' if view["image"] else "<p>No usable image</p>"
                views_html.append(f"<figure>{image_html}<figcaption>{html.escape(label)}<br>{html.escape(timing)}</figcaption></figure>")
                event["views"].append(view)
            tiles.append(np.concatenate(tiles_row, axis=1))
            sections.append(f"<section><h2>{html.escape(event['name'])} · {event['t']:.3f}s</h2>"
                            f"<p>{html.escape(event['annotation'])}</p><div class='views'>{''.join(views_html)}</div></section>")
    finally:
        for source in sources.values():
            source.release()
    contact_sheet = np.concatenate(tiles, axis=0)
    if not cv2.imwrite(str(out / "contact_sheet.jpg"), contact_sheet):
        raise RuntimeError("failed writing contact sheet")
    present = {event["name"] for event in events}
    summary = {"schema_version": 1, "episode_id": episode["manifest"]["episode_id"],
               "telemetry_time_offset_s": episode["manifest"]["telemetry"].get("offset_s", 0),
               "clock": episode["manifest"]["clock"],
               "source_assets": {
                   "episode_manifest": {"path": Path(episode_path).name, "sha256": file_sha256(Path(episode_path))},
                   "telemetry": {"path": episode["manifest"]["telemetry"]["path"],
                                 "sha256": file_sha256(asset_path(episode["root"], episode["manifest"]["telemetry"]["path"]))},
                   "cameras": [{"camera_id": c["camera_id"],
                                "video": {"path": c["video"], "sha256": file_sha256(c["video_path"])},
                                "frames": {"path": c["frames"], "sha256": file_sha256(asset_path(episode["root"], c["frames"]))}}
                               for c in episode["cameras"]]},
               "provenance": episode["manifest"]["provenance"], "phases": events,
               "missing_phase_labels": sorted({"before", "grasp", "lift", "tip", "release", "after"} - present),
               "alignment": alignment, "outcome": {"status": "unknown", "evidence": []},
               "contact_sheet": "contact_sheet.jpg", "contact_sheet_html": "index.html",
               "limitations": ["Phase names reflect checkpoints/commands, not validated physical outcomes",
                               "Host receipt timestamps do not establish camera exposure synchronization",
                               "Stale selected frames are visible for inspection but must not authorize adaptation"]}
    write_json(out / "summary.json", summary)
    body = """<!doctype html><html lang="en"><meta charset="utf-8"><title>OpenArms episode evidence</title>
<style>body{font:16px system-ui;background:#111827;color:#e5e7eb;margin:2rem;max-width:1100px}h1,h2{color:#93c5fd}
.views{display:flex;flex-wrap:wrap}figure{margin:0 1rem 1rem 0;max-width:480px}img{width:100%}figcaption{line-height:1.5}
section{border-top:1px solid #374151;padding:1rem 0}a{color:#93c5fd}</style>"""
    body += f"<h1>{html.escape(summary['episode_id'])}</h1><p>Evidence source: <strong>{html.escape(summary['provenance'])}</strong>. Outcome: UNKNOWN.</p>"
    body += "<p>Checkpoint annotations describe operator labels and commanded events. They do not prove grip, delivery, clearance, or spill absence.</p><p><a href='summary.json'>Machine-readable summary and alignment</a></p>"
    body += "".join(sections) + "</html>"
    (out / "index.html").write_text(body)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-skew-s", type=float, default=.1)
    args = parser.parse_args()
    result = summarize_episode(args.episode, args.out, args.max_skew_s)
    print(json.dumps({"episode_id": result["episode_id"], "phases": len(result["phases"]),
                      "outcome": "unknown", "summary": str(args.out / "summary.json")}))


if __name__ == "__main__":
    main()
