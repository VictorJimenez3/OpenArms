import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench_vision.capture import (_camera_config, capture_camera, capture_live, finalize_episode,
                                  image_dependencies, make_fixture, replay_frame)
from bench_vision.episode import load_episode
from bench_vision.keyframes import summarize_episode


class ConfigTests(unittest.TestCase):
    def test_device_alias_must_be_verified(self):
        cameras = [{"camera_id": "overview-serial1", "device": 0}, {"camera_id": "side-serial2", "device": 1}]
        with self.assertRaisesRegex(ValueError, "verify"):
            _camera_config(cameras)
        for camera in cameras:
            camera["identity_verified"] = True
        _camera_config(cameras)

    def test_same_device_twice_rejected(self):
        cameras = [{"camera_id": "first", "device": 0, "identity_verified": True},
                   {"camera_id": "second", "device": 0, "identity_verified": True}]
        with self.assertRaisesRegex(ValueError, "distinct"):
            _camera_config(cameras)


class CaptureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.cv2, cls.np = image_dependencies()
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_encoded_fixture_replay_and_summary(self):
        manifest = make_fixture(self.root / "fixture")
        episode = load_episode(manifest)
        self.assertEqual(episode["manifest"]["provenance"], "synthetic")
        self.assertEqual(replay_frame(manifest, "fixture-overview", 5).shape, (320, 480, 3))
        summary = summarize_episode(manifest, self.root / "summary")
        self.assertEqual(summary["outcome"]["status"], "unknown")
        self.assertEqual(summary["missing_phase_labels"], [])
        self.assertEqual(summary["alignment"]["cameras"][1]["dropped_reads"], 3)
        self.assertTrue((self.root / "summary/contact_sheet.jpg").exists())
        self.assertTrue((self.root / "summary/index.html").exists())
        for event in summary["phases"]:
            self.assertEqual(len(event["views"]), 2)
            self.assertTrue(all(view["image"] for view in event["views"]))
        with self.assertRaises(ValueError):
            replay_frame(manifest, "fixture-overview", 9999)
        with self.assertRaises(FileExistsError):
            make_fixture(self.root / "fixture")

    def test_corrupt_video_cannot_produce_usable_keyframe(self):
        manifest = make_fixture(self.root / "fixture")
        (manifest.parent / "side.avi").write_bytes(b"corrupt")
        summary = summarize_episode(manifest, self.root / "summary")
        for phase in summary["phases"]:
            self.assertEqual(phase["views"][1]["status"], "decode_failed")
            self.assertIsNone(phase["views"][1]["image"])

    def test_fake_frame_source_records_drops_without_video_index_gap(self):
        frame = self.np.zeros((64, 80, 3), dtype=self.np.uint8)
        class Clock:
            now = 100.
            def __call__(self): return self.now
            def sleep(self, seconds): self.now += seconds
        class Source:
            released = False
            index = 0
            def read(self):
                self.index += 1
                return (False, None) if self.index == 2 else (True, frame)
            def release(self): self.released = True
        clock, source = Clock(), Source()
        result = capture_camera(source, self.root,
                                {"camera_id": "fake", "video": "fake.avi", "frames": "fake.jsonl", "fps_nominal": 10},
                                duration_s=.35, clock=clock, sleep=clock.sleep)
        self.assertIsNone(result["error"])
        self.assertTrue(source.released)
        rows = [json.loads(line) for line in (self.root / "fake.jsonl").read_text().splitlines()]
        self.assertEqual([row["frame_index"] for row in rows], [0, None, 1, 2])
        self.assertEqual(rows[1]["status"], "dropped")
        self.assertEqual(result["frames_written"], 3)

    def test_fake_capture_preserves_failure_receipt(self):
        class Source:
            released = False
            def read(self): raise OSError("fake unplug")
            def release(self): self.released = True
        source = Source()
        result = capture_camera(source, self.root,
                                {"camera_id": "fake", "video": "fake.avi", "frames": "fake.jsonl", "fps_nominal": 10},
                                duration_s=.1)
        self.assertIn("fake unplug", result["error"])
        self.assertTrue(source.released)

    def test_partial_camera_capture_requires_explicit_telemetry_finalization(self):
        class Source:
            def isOpened(self): return True
            def set(self, *_): pass
            def read(self): raise OSError("fake unplug")
            def release(self): pass
        cameras = [{"camera_id": "one", "device": 0, "identity_verified": True},
                   {"camera_id": "two", "device": 1, "identity_verified": True}]
        with patch.object(self.cv2, "VideoCapture", side_effect=lambda *_: Source()):
            path = capture_live(cameras, self.root / "partial", duration_s=.1)
        manifest = json.loads(path.read_text())
        self.assertFalse(manifest["capture_complete"])
        self.assertFalse(manifest["telemetry_complete"])
        self.assertEqual(len(manifest["camera_receipts"]), 2)
        with self.assertRaisesRegex(ValueError, "not finalized"):
            load_episode(path)
        trace = self.root / "finished.jsonl"
        trace.write_text('{"t":1,"event":"sample","state":{}}\n')
        with self.assertRaisesRegex(ValueError, "recorder has exited"):
            finalize_episode(path, trace, same_host_clock=True)
        with self.assertRaisesRegex(ValueError, "same host/boot"):
            finalize_episode(path, trace, recorder_finished=True)
        finalize_episode(path, trace, recorder_finished=True, same_host_clock=True)
        episode = load_episode(path)
        self.assertFalse(episode["manifest"]["capture_complete"])
        self.assertTrue(episode["manifest"]["telemetry_complete"])
        self.assertTrue(all(camera["video_missing"] for camera in episode["cameras"]))
        with self.assertRaisesRegex(ValueError, "already finalized"):
            finalize_episode(path, trace, recorder_finished=True, same_host_clock=True)


if __name__ == "__main__":
    unittest.main()
