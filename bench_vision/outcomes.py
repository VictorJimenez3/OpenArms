"""Attach existing pour receipts to episode evidence without inferring success.

This module only reads and writes files; it never imports robot control code.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


CHECKS = ("grip_clearance", "delivery", "spill", "cup_return", "home_reset")
CHECK_MEANINGS = {
    "grip_clearance": "Cup remained securely held and path was clear",
    "delivery": "Intended delivery was independently observed",
    "spill": "No spill was independently observed; passed means no spill",
    "cup_return": "Cup was returned to its intended fixture",
    "home_reset": "HOME and the required reset were independently verified",
}
SUMMARY_PROVENANCE = {"physical", "recorded", "synthetic", "fake", "simulated", "predicted", "unknown"}


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def _load_json(raw: str):
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON field: {key}")
            value[key] = item
        return value
    return json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=unique_object)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def parse_receipt(raw: bytes) -> dict:
    """Parse one closed pour_once JSONL receipt, preserving control vs observation.

    A syntactically complete but interrupted receipt may lack a result or observer
    note. It remains usable diagnostic evidence with an unknown observed outcome.
    A missing final newline is rejected because pour_once flushes whole lines.
    """
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("receipt is empty or truncated (missing final newline)")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("receipt must be UTF-8 JSONL") from exc
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = _load_json(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed receipt JSON at line {number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"receipt line {number} must be an object")
        _text(row.get("event"), "receipt event")
        rows.append((number, row))
    requests = [(n, row) for n, row in rows if row["event"] == "request"]
    results = [(n, row) for n, row in rows if row["event"] == "result"]
    if len(requests) != 1 or not rows or rows[0][1]["event"] != "request":
        raise ValueError("receipt must start with exactly one request")
    if len(results) > 1:
        raise ValueError("receipt has conflicting result rows")
    request = requests[0][1]
    backend = request.get("backend")
    if backend not in {"physical", "fake"}:
        raise ValueError("receipt request backend must explicitly be physical or fake")
    if any(row.get("backend", backend) != backend for _, row in rows):
        raise ValueError("receipt contains conflicting backend provenance")
    observations = []
    for number, row in rows:
        if row["event"] == "operator_observation":
            if not isinstance(row.get("text"), str):
                raise ValueError("operator_observation text must be a string")
            observations.append({"line": number, "text": row["text"], "time": row.get("time"),
                                 "provenance": backend, "reference": f"operator_observation:{number}"})
    result = copy.deepcopy(results[0][1]) if results else None
    if result is not None:
        _text(result.get("status"), "result status")
    return {"backend": backend, "mode": request.get("mode"),
            "controller_result": result,
            "controller_status": result["status"] if result else "unknown",
            "operator_observations": observations,
            "diagnostic_events": [row["event"] for _, row in rows if row["event"] in {"error", "interrupted"}],
            "sha256": hashlib.sha256(raw).hexdigest(), "line_count": len(lines)}


def _assessment(checks: dict | None, reference: str | None, receipt: dict, summary: dict) -> dict:
    if checks is None:
        if reference is not None:
            raise ValueError("checks-reference requires structured checks")
        return {"status": "unknown", "checks": {key: "unknown" for key in CHECKS}, "reference": None}
    if not isinstance(checks, dict) or set(checks) - set(CHECKS):
        raise ValueError("checks must map only the five documented outcome checks")
    merged = {key: checks.get(key, "unknown") for key in CHECKS}
    if any(not isinstance(value, str) or value not in {"passed", "failed", "unknown"} for value in merged.values()):
        raise ValueError("check values must be passed, failed or unknown")
    known = any(value != "unknown" for value in merged.values())
    if known:
        if receipt["backend"] != "physical":
            raise ValueError("fake receipt cannot substantiate physical outcome checks")
        if summary["provenance"] not in {"physical", "recorded"}:
            raise ValueError("synthetic/fake/simulated/unknown summary cannot be elevated to physical outcome")
        _text(reference, "checks-reference")
        matches = [row for row in receipt["operator_observations"] if row["reference"] == reference and row["text"].strip()]
        if not matches:
            raise ValueError("checks-reference must identify an existing nonempty operator_observation:LINE")
    status = "failed" if "failed" in merged.values() else "passed" if all(v == "passed" for v in merged.values()) else "unknown"
    return {"status": status, "checks": merged, "reference": reference}


def attach_receipt(summary_path: str | Path, receipt_path: str | Path, out_path: str | Path, *,
                   observer: str, checks: dict | None = None, checks_reference: str | None = None) -> dict:
    """Write a new summary and a hash-named receipt copy, never overwrite inputs.

    The operator explicitly associates this receipt with this episode: existing
    pour receipts do not carry episode IDs, so association is not auto-verified.
    """
    _text(observer, "observer")
    summary_path, receipt_path, out_path = map(Path, (summary_path, receipt_path, out_path))
    if out_path.parent.resolve() != summary_path.parent.resolve():
        raise ValueError("new summary must stay in the same directory to preserve relative image evidence")
    if out_path.exists():
        raise FileExistsError("output summary already exists; choose a new version filename")
    summary_raw, receipt_raw = summary_path.read_bytes(), receipt_path.read_bytes()
    summary = _load_json(summary_raw.decode("utf-8"))
    if not isinstance(summary, dict) or summary.get("schema_version") != 1:
        raise ValueError("summary needs schema_version 1")
    _text(summary.get("episode_id"), "episode_id")
    if summary.get("provenance") not in SUMMARY_PROVENANCE:
        raise ValueError("summary needs explicit provenance")
    receipt = parse_receipt(receipt_raw)
    assessment = _assessment(checks, checks_reference, receipt, summary)
    filename = f"receipt-{receipt['sha256']}.jsonl"
    reference = f"{filename}#sha256={receipt['sha256']}"
    evidence = {"provenance": receipt["backend"], "observer": observer, "reference": reference,
                "kind": "operator_receipt", "controller_status": receipt["controller_status"],
                "controller_result": receipt["controller_result"],
                "operator_observations": receipt["operator_observations"],
                "structured_checks": assessment["checks"], "checks_reference": assessment["reference"],
                "check_meanings": CHECK_MEANINGS,
                "association": "Operator attached; original receipt has no episode identity",
                "physical_success_inferred_from_prose": False}
    result = copy.deepcopy(summary)
    result["prior_outcome"] = copy.deepcopy(summary.get("outcome", {"status": "unknown", "evidence": []}))
    result["outcome"] = {"status": assessment["status"], "evidence": [evidence]}
    result.setdefault("receipt_attachments", []).append({"filename": filename, "sha256": receipt["sha256"],
        "backend": receipt["backend"], "mode": receipt["mode"], "observer": observer,
        "controller_status": receipt["controller_status"], "diagnostic_events": receipt["diagnostic_events"]})
    result["parent_summary"] = {"filename": summary_path.name, "sha256": hashlib.sha256(summary_raw).hexdigest()}
    serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    destination = out_path.parent / filename
    try:
        with destination.open("xb") as copy_file:
            copy_file.write(receipt_raw)
    except FileExistsError:
        if destination.read_bytes() != receipt_raw:
            raise ValueError("receipt destination collision; existing evidence was not overwritten")
    with out_path.open("x") as output:
        output.write(serialized)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    attach = sub.add_parser("attach-receipt")
    attach.add_argument("--summary", type=Path, required=True)
    attach.add_argument("--receipt", type=Path, required=True)
    attach.add_argument("--out", type=Path, required=True)
    attach.add_argument("--observer", required=True)
    attach.add_argument("--checks", type=Path, help="JSON mapping the five checks to passed/failed/unknown")
    attach.add_argument("--checks-reference", help="explicit supporting operator_observation:LINE in the receipt")
    args = parser.parse_args()
    checks = _load_json(args.checks.read_text()) if args.checks else None
    result = attach_receipt(args.summary, args.receipt, args.out, observer=args.observer,
                            checks=checks, checks_reference=args.checks_reference)
    print(json.dumps({"episode_id": result["episode_id"], "outcome": result["outcome"]["status"],
                      "controller_status": result["receipt_attachments"][-1]["controller_status"],
                      "summary": str(args.out)}))


if __name__ == "__main__":
    main()
