import copy
import json
from pathlib import Path
import tempfile
import unittest

from bench_vision.episode import align_episode, asset_path, load_episode, nearest_frame
from bench_vision.keyframes import select_events


def minimal_episode(root: Path):
    trace = [{"t": 10., "event": "sample", "state": {"gripper.pos": 70}},
             {"t": 10.1, "event": "checkpoint", "name": "HOME", "state": {}},
             {"t": 10.2, "event": "sample", "state": {}}]
    (root / "trace.jsonl").write_text("".join(json.dumps(x) + "\n" for x in trace))
    cameras = []
    for camera_id in ("overview", "side"):
        (root / f"{camera_id}.avi").write_bytes(b"placeholder; unit tests do not decode")
        rows = [{"t": 10.01, "frame_index": 0, "status": "ok"},
                {"t": 10.11, "frame_index": None, "status": "dropped"},
                {"t": 10.21, "frame_index": 1, "status": "ok"}]
        (root / f"{camera_id}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
        cameras.append({"camera_id": camera_id, "video": f"{camera_id}.avi", "frames": f"{camera_id}.jsonl",
                        "clock_domain": "test-clock", "fps_nominal": 10})
    manifest = {"schema_version": 1, "episode_id": "test", "provenance": "synthetic",
                "clock": {"domain": "test-clock", "units": "seconds", "hardware_synchronized": False},
                "telemetry": {"path": "trace.jsonl", "clock_domain": "test-clock"}, "cameras": cameras}
    path = root / "episode.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path, self.manifest = minimal_episode(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.manifest))

    def test_alignment_reports_drops_and_stale(self):
        report = align_episode(self.path, .05)
        self.assertFalse(report["hardware_synchronized"])
        self.assertEqual(report["cameras"][0]["dropped_reads"], 1)
        self.assertEqual(report["cameras"][0]["estimated_missing_intervals"], 1)
        self.assertEqual(report["cameras"][0]["stale_rows"], 1)
        self.assertEqual(report["cameras"][0]["aligned_rows"], 2)
        self.assertAlmostEqual(report["paired_frames"][0]["views"][0]["skew_s"], .01)

    def test_missing_camera_files_explicit(self):
        (self.root / "side.avi").unlink()
        (self.root / "side.jsonl").unlink()
        report = align_episode(self.path)
        self.assertEqual(report["cameras"][1]["missing_rows"], 3)
        self.assertTrue(report["cameras"][1]["video_missing"])
        self.assertIsNone(report["paired_frames"][0]["intercamera_skew_s"])

    def test_no_frame_reuse_past_skew_limit(self):
        camera = load_episode(self.path)["cameras"][0]
        self.assertEqual(nearest_frame(camera, 20)["status"], "stale")

    def test_remote_clock_requires_measured_offset(self):
        self.manifest["cameras"][0]["clock_domain"] = "remote"
        self.save()
        with self.assertRaisesRegex(ValueError, "different clocks"):
            load_episode(self.path)
        self.manifest["cameras"][0].update(offset_s=0, offset_uncertainty_s=.2)
        self.save()
        self.assertEqual(align_episode(self.path)["cameras"][0]["stale_rows"], 3)

    def test_remote_offset_is_applied(self):
        self.manifest["cameras"][0].update(clock_domain="remote", offset_s=-.2, offset_uncertainty_s=.001)
        self.save()
        camera = load_episode(self.path)["cameras"][0]
        view = nearest_frame(camera, 10.0, .02)
        self.assertEqual(view["frame_index"], 1)
        self.assertEqual(view["status"], "ok")

    def test_bad_timestamps_rejected(self):
        for data in ({"t": float("nan"), "event": "sample"}, {"t": True, "event": "sample"}):
            (self.root / "trace.jsonl").write_text(json.dumps(data) + "\n")
            with self.assertRaisesRegex(ValueError, "finite"):
                load_episode(self.path)

    def test_backwards_timestamps_rejected(self):
        (self.root / "overview.jsonl").write_text('{"t":11,"status":"ok","frame_index":0}\n{"t":10,"status":"ok","frame_index":1}\n')
        with self.assertRaisesRegex(ValueError, "backwards"):
            load_episode(self.path)

    def test_bad_frame_index_rejected(self):
        (self.root / "overview.jsonl").write_text('{"t":10,"status":"ok","frame_index":2}\n')
        with self.assertRaisesRegex(ValueError, "contiguous"):
            load_episode(self.path)

    def test_path_escape_and_symlink_rejected(self):
        for name in ("../outside", "/tmp/absolute"):
            with self.assertRaises(ValueError):
                asset_path(self.root, name)
        (self.root / "escape").symlink_to("/tmp")
        with self.assertRaises(ValueError):
            asset_path(self.root, "escape/file")

    def test_camera_id_cannot_escape_summary_output(self):
        self.manifest["cameras"][0]["camera_id"] = "../../escape"
        self.save()
        with self.assertRaisesRegex(ValueError, "filename-safe"):
            load_episode(self.path)

    def test_duplicate_camera_identity_rejected(self):
        self.manifest["cameras"][1]["camera_id"] = "overview"
        self.save()
        with self.assertRaisesRegex(ValueError, "unique"):
            load_episode(self.path)

    def test_empty_trace_rejected(self):
        (self.root / "trace.jsonl").write_text("")
        with self.assertRaisesRegex(ValueError, "empty"):
            load_episode(self.path)

    def test_hardware_synchronization_claim_rejected(self):
        self.manifest["clock"]["hardware_synchronized"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "synchronization"):
            load_episode(self.path)

    def test_invalid_alignment_tolerance_rejected(self):
        for tolerance in (-1, float("nan")):
            with self.assertRaises(ValueError):
                align_episode(self.path, tolerance)


class EventTests(unittest.TestCase):
    def test_release_uses_recorded_gripper_polarity(self):
        for opened, closed in ((70, 20), (5, 90)):
            trace = [{"t": 0., "event": "checkpoint", "name": "open", "command": {"gripper.pos": opened}},
                     {"t": 1., "event": "checkpoint", "name": "cup", "command": {"gripper.pos": closed}},
                     {"t": 1.1, "event": "sample", "command": {"gripper.pos": closed}},
                     {"t": 2., "event": "sample", "command": {"gripper.pos": opened}}]
            events = select_events(trace)
            release = next(event for event in events if event["name"] == "release")
            self.assertEqual(release["event_source"], "inferred_gripper")
            self.assertEqual(release["t"], 2.)
            self.assertFalse(release["verified_outcome"])

    def test_absent_release_is_not_invented(self):
        events = select_events([{"t": 0., "event": "checkpoint", "name": "cup", "state": {}}])
        self.assertNotIn("release", {event["name"] for event in events})
        self.assertTrue(all(not event["verified_outcome"] for event in events))


if __name__ == "__main__":
    unittest.main()
