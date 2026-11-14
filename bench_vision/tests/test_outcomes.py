import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from bench_vision.outcomes import CHECKS, attach_receipt, parse_receipt


def receipt_bytes(backend="physical", observations=True, result=True):
    rows = [{"event": "request", "backend": backend, "mode": "water", "poses": "/private/bench/poses.json"}]
    if result:
        rows.append({"event": "result", "status": "executed", "steps_done": ["pick", "pour", "return_cup", "home"]})
    if observations:
        rows.append({"event": "operator_observation", "text": "Looked successful; inspect measurements separately"})
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.summary = self.root / "summary.json"
        self.receipt = self.root / "original.jsonl"
        self.out = self.root / "summary-observed.json"
        self.summary.write_text(json.dumps({"schema_version": 1, "episode_id": "test", "provenance": "physical",
                                           "phases": [{"views": [{"image": "frames/image.jpg"}]}],
                                           "outcome": {"status": "unknown", "evidence": []}}))
        self.receipt.write_bytes(receipt_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def attach(self, **kwargs):
        return attach_receipt(self.summary, self.receipt, self.out, observer="Bench observer", **kwargs)

    def test_completed_and_positive_prose_remain_unknown(self):
        before = self.summary.read_bytes()
        result = self.attach()
        self.assertEqual(result["outcome"]["status"], "unknown")
        evidence = result["outcome"]["evidence"][0]
        self.assertEqual(evidence["controller_status"], "executed")
        self.assertIn("Looked successful", evidence["operator_observations"][0]["text"])
        self.assertFalse(evidence["physical_success_inferred_from_prose"])
        self.assertEqual(self.summary.read_bytes(), before)
        self.assertEqual(result["phases"][0]["views"][0]["image"], "frames/image.jpg")
        self.assertNotIn("/private/bench", self.out.read_text())

    def test_original_receipt_is_copied_and_bound(self):
        result = self.attach()
        attachment = result["receipt_attachments"][0]
        self.assertEqual(attachment["sha256"], hashlib.sha256(self.receipt.read_bytes()).hexdigest())
        self.assertEqual((self.root / attachment["filename"]).read_bytes(), self.receipt.read_bytes())
        self.assertEqual(result["parent_summary"]["filename"], "summary.json")
        self.assertFalse(Path(attachment["filename"]).is_absolute())

    def test_fake_completed_cannot_pass_physical_checks(self):
        self.receipt.write_bytes(receipt_bytes(backend="fake"))
        with self.assertRaisesRegex(ValueError, "fake receipt"):
            self.attach(checks={key: "passed" for key in CHECKS}, checks_reference="operator_observation:3")
        result = self.attach()
        self.assertEqual(result["outcome"]["status"], "unknown")
        self.assertEqual(result["outcome"]["evidence"][0]["provenance"], "fake")

    def test_structured_explicit_physical_checks_can_pass(self):
        result = self.attach(checks={key: "passed" for key in CHECKS}, checks_reference="operator_observation:3")
        self.assertEqual(result["outcome"]["status"], "passed")
        evidence = result["outcome"]["evidence"][0]
        self.assertEqual(evidence["observer"], "Bench observer")
        self.assertEqual(evidence["checks_reference"], "operator_observation:3")
        self.assertIn("passed means no spill", evidence["check_meanings"]["spill"])

    def test_partial_checks_unknown_and_explicit_failure_failed(self):
        result = self.attach(checks={"delivery": "passed"}, checks_reference="operator_observation:3")
        self.assertEqual(result["outcome"]["status"], "unknown")
        other = self.root / "summary-failed.json"
        result = attach_receipt(self.summary, self.receipt, other, observer="Bench observer",
                                checks={"spill": "failed"}, checks_reference="operator_observation:3")
        self.assertEqual(result["outcome"]["status"], "failed")

    def test_checks_require_actual_nonempty_observation_reference(self):
        for reference in (None, "operator_observation:2", "made-up", "operator_observation:999"):
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    self.attach(checks={"delivery": "passed"}, checks_reference=reference)
        self.receipt.write_bytes(receipt_bytes(observations=False))
        with self.assertRaisesRegex(ValueError, "existing nonempty"):
            self.attach(checks={"delivery": "passed"}, checks_reference="operator_observation:3")
        self.assertEqual(self.attach()["outcome"]["status"], "unknown")

    def test_missing_result_and_observations_are_diagnostic_unknown(self):
        self.receipt.write_bytes(receipt_bytes(observations=False, result=False) + b'{"event":"interrupted"}\n')
        result = self.attach()
        self.assertEqual(result["outcome"]["status"], "unknown")
        self.assertEqual(result["receipt_attachments"][0]["controller_status"], "unknown")
        self.assertEqual(result["receipt_attachments"][0]["diagnostic_events"], ["interrupted"])

    def test_synthetic_summary_cannot_be_elevated_by_physical_receipt(self):
        for provenance in ("synthetic", "fake", "simulated", "predicted", "unknown"):
            summary = json.loads(self.summary.read_text())
            summary["provenance"] = provenance
            self.summary.write_text(json.dumps(summary))
            with self.subTest(provenance=provenance):
                with self.assertRaisesRegex(ValueError, "cannot be elevated"):
                    self.attach(checks={"delivery": "passed"}, checks_reference="operator_observation:3")

    def test_conflicting_receipt_provenance_and_duplicate_request_rejected(self):
        for raw in (receipt_bytes() + b'{"event":"result","backend":"fake","status":"executed"}\n',
                    receipt_bytes() + b'{"event":"request","backend":"fake"}\n',
                    b'{"event":"request","backend":"fake","backend":"physical"}\n'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_receipt(raw)

    def test_malformed_or_truncated_receipt_rejected(self):
        for raw in (b"", b"\n", b"not json\n", b'{"event":"request"', receipt_bytes().rstrip(b"\n"),
                    b'[]\n', b'{"event":"request","backend":"physical","bad":NaN}\n'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_receipt(raw)

    def test_output_is_exclusive_and_stays_with_image_assets(self):
        self.attach()
        with self.assertRaises(FileExistsError):
            self.attach()
        with self.assertRaisesRegex(ValueError, "same directory"):
            attach_receipt(self.summary, self.receipt, self.root / "other" / "summary.json", observer="Observer")

    def test_bad_checks_and_missing_observer_rejected(self):
        for checks in ({"delivery": True}, {"delivery": {}}, {"chemistry": "passed"}, [], {"spill": "success"}):
            with self.subTest(checks=checks):
                with self.assertRaises(ValueError):
                    self.attach(checks=checks, checks_reference="operator_observation:3")
        with self.assertRaisesRegex(ValueError, "observer"):
            attach_receipt(self.summary, self.receipt, self.out, observer="")

    def test_hash_named_receipt_collision_cannot_overwrite(self):
        sha = hashlib.sha256(self.receipt.read_bytes()).hexdigest()
        target = self.root / f"receipt-{sha}.jsonl"
        target.write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "collision"):
            self.attach()
        self.assertEqual(target.read_bytes(), b"different")
        self.assertFalse(self.out.exists())

    def test_cli_attaches_receipt_without_promoting_command_completion(self):
        completed = subprocess.run([sys.executable, "-m", "bench_vision.outcomes", "attach-receipt",
                                    "--summary", str(self.summary), "--receipt", str(self.receipt),
                                    "--out", str(self.out), "--observer", "Test observer"],
                                   capture_output=True, text=True, check=True)
        status = json.loads(completed.stdout)
        self.assertEqual(status["outcome"], "unknown")
        self.assertEqual(status["controller_status"], "executed")

    def test_attachment_compiles_new_candidate_and_retains_baseline(self):
        from bench_vision.skills import compile_candidate
        from bench_vision.tests.test_skills import inputs
        poses, trace, summary, context = inputs()
        baseline = compile_candidate(poses, trace, summary, context)
        self.summary.write_text(json.dumps(summary))
        # A fake execution receipt is useful evidence but never physical success.
        self.receipt.write_bytes(receipt_bytes(backend="fake"))
        revised_summary = self.attach()
        candidate = compile_candidate(poses, trace, revised_summary, context, baseline=baseline)
        self.assertNotEqual(candidate["version"], baseline["version"])
        self.assertEqual(candidate["rollback"]["baseline_version"], baseline["version"])
        self.assertEqual(candidate["outcome"]["status"], "unknown")
        self.assertEqual(candidate["outcome"]["evidence"][0]["provenance"], "fake")


if __name__ == "__main__":
    unittest.main()
