"""Authenticated, deterministic student-loop trace against the real MuJoCo adapter.

These tests deliberately inject a small expert instead of calling a provider.  The
HTTP session, consent checks, task loop, controller receipt, and independent pixel
observer still run through the production paths.  This keeps the simulator smoke
trace reproducible and cheap enough to run while provider-backed cold/warm traces
are evaluated separately.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from agentic.openarms_lab.app import create_app
from agentic.openarms_lab.mujoco_backend import MujocoBackend
from agentic.openarms_lab.mujoco_scene import MujocoSceneService
from agentic.openarms_lab.runtime import Lab


SCOPE = "mujoco-student-trace-v1"


def _plan():
    return {
        "skill_definition": {
            "skill_id": "mujoco_prepared_indicator",
            "name": "Prepared indicator sample",
            "intent": "Run one prepared sample through the fixed MuJoCo indicator setup and read the result.",
            "retrieval_examples": ["test prepared {condition}"],
            "parameter_schema": {
                "condition": {
                    "type": "string",
                    "enum": ["vinegar", "baking_soda", "water"],
                }
            },
            "preconditions": {"fresh_scene": True, "labels": ["receiver"]},
            "steps": [
                {"operation": "inspect_scene", "arguments": {"view": "primary"}},
                {
                    "operation": "mock_prepared_sample",
                    "arguments": {
                        "condition_id": "$condition",
                        "source": "A",
                        "destination": "C",
                    },
                },
                {"operation": "observe", "arguments": {"view": "primary"}},
            ],
            "expected_state": {"at": "HOME"},
            "outcome_checks": [{"feature": "readable", "expected": True}],
            "limitations": [
                "This is a fixed prepared-sample MuJoCo fixture; it is not hardware execution."
            ],
        },
        "bindings": {"condition": "vinegar"},
    }


class DeterministicExpert:
    """Provide a valid plan without making a provider call."""

    def __init__(self):
        self.phases = []
        self.tool_calls = []

    async def run(self, context, *, tool_handler, emit, cancel_event):
        self.phases.append(context["phase"])
        if context["phase"] == "planning":
            frame = context["images"][0]["evidence_id"]
            result = await tool_handler(
                "localize_objects", {"evidence_id": frame, "labels": ["receiver"]}
            )
            self.tool_calls.append(result)
            assert result["verified_labels"] == ["receiver"]
            return {
                "kind": "plan",
                "summary": "I will run the prepared vinegar sample and read the receiver independently.",
                "payload": _plan(),
                "provider": "DETERMINISTIC_TEST",
                "model": "DETERMINISTIC_TEST",
                "reasoning_effort": "none",
                "calls": 0,
                "usage": {"total_tokens": 0},
                "elapsed_ms": 0,
                "tool_receipts": [],
            }
        return {
            "kind": "complete",
            "summary": "Continue the approved plan.",
            "payload": {"continue": True},
            "provider": "DETERMINISTIC_TEST",
            "model": "DETERMINISTIC_TEST",
            "reasoning_effort": "none",
            "calls": 0,
            "usage": {"total_tokens": 0},
            "elapsed_ms": 0,
            "tool_receipts": [],
        }


def _session(client):
    response = client.post("/api/sessions")
    assert response.status_code == 200, response.text
    body = response.json()
    sid = body["session_id"]
    url = f"/api/sessions/{sid}"
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return body, url, headers


def _wait_for(client, url, headers, predicate, timeout=60):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        latest = response.json()
        if predicate(latest):
            return latest
        time.sleep(0.02)
    pytest.fail(f"Timed out waiting for simulator state: {latest}")


@pytest.fixture
def mujoco_client(tmp_path):
    pytest.importorskip("mujoco")
    scene = MujocoSceneService(tmp_path / "scene-evidence")
    expert = DeterministicExpert()
    lab = Lab(
        tmp_path / "lab-data",
        expert=expert,
        perception=scene,
        execution_scope=SCOPE,
        backend_factory=lambda: MujocoBackend(scene),
        execution_timeout=60,
        expert_timeout=10,
    )
    with TestClient(create_app(lab, access_path=tmp_path / "access.db")) as client:
        yield client, lab, expert


def test_authenticated_prepared_action_has_controller_and_pixel_receipts(mujoco_client):
    client, lab, expert = mujoco_client
    session, url, headers = _session(client)
    sid = session["session_id"]

    chosen = client.post(
        url + "/condition", json={"condition_id": "vinegar"}, headers=headers
    )
    assert chosen.status_code == 200, chosen.text
    queued = client.post(
        url + "/request",
        json={"text": "Test the prepared vinegar sample.", "client_request_id": "trace-1"},
        headers=headers,
    )
    assert queued.status_code == 200, queued.text

    pending = _wait_for(client, url, headers, lambda state: state["pending"] is not None)
    proposal = pending["pending"]
    assert proposal["plan"]["execution_scope"] == SCOPE
    assert proposal["plan"]["steps"][1]["operation"] == "mock_prepared_sample"

    binding = {
        "request_id": proposal["request_id"],
        "proposal_version": proposal["proposal_version"],
    }
    presented = client.post(url + "/present", json=binding, headers=headers)
    assert presented.status_code == 200, presented.text
    confirmed = client.post(url + "/confirm", json=binding, headers=headers)
    assert confirmed.status_code == 200, confirmed.text

    state = _wait_for(
        client,
        url,
        headers,
        lambda snapshot: bool(snapshot["tasks"])
        and snapshot["tasks"][-1]["status"] in {"completed", "failed"},
    )
    task = state["tasks"][-1]
    assert task["status"] == "completed", task
    assert task["dispatched_action"] is True
    assert task["route"] == "expert"
    assert expert.phases[0] == "planning"
    assert set(expert.phases[1:]) <= {"execution_feedback"}
    assert expert.tool_calls and expert.tool_calls[0]["provenance"] == "SIMULATED"

    execution = task["execution"]
    assert len(execution) == 1
    receipt = execution[0]
    assert receipt["backend"] == "mujoco"
    assert receipt["status"] == "completed"
    assert receipt["controller_completed"] is True
    assert receipt["physical_execution"] is False
    assert receipt["provenance"] == "SIMULATED"
    assert receipt["simulation"]["dose_count"] == 1
    assert receipt["simulation"]["engine"] == "MuJoCo"
    assert receipt["simulation"]["frame_count"] > 100
    assert receipt["simulation"]["video_url"].startswith(f"/api/sessions/{sid}/media/")

    observation = state["observations"][-1]
    assert observation["status"] == "observed"
    assert observation["provenance"] == "SIMULATED"
    assert observation["features"]["readable"] is True
    assert observation["receipt"]["observer_version"].startswith("mujoco-")
    assert observation["evidence"]

    media = client.get(receipt["simulation"]["video_url"], headers=headers)
    assert media.status_code == 200, media.text
    assert media.headers["content-type"].startswith("video/mp4")
    assert len(media.content) > 1000

    backend = lab.backends[sid]
    assert isinstance(backend, MujocoBackend)
    assert backend.executions == 1


def test_stop_revokes_presented_mujoco_consent_without_dispatch(mujoco_client):
    client, lab, _expert = mujoco_client
    session, url, headers = _session(client)
    sid = session["session_id"]
    assert client.post(
        url + "/condition", json={"condition_id": "vinegar"}, headers=headers
    ).status_code == 200
    assert client.post(
        url + "/request", json={"text": "Test the prepared vinegar sample."}, headers=headers
    ).status_code == 200
    pending = _wait_for(client, url, headers, lambda state: state["pending"] is not None)
    proposal = pending["pending"]
    binding = {
        "request_id": proposal["request_id"],
        "proposal_version": proposal["proposal_version"],
    }
    assert client.post(url + "/present", json=binding, headers=headers).status_code == 200
    stopped = client.post(url + "/stop", headers=headers)
    assert stopped.status_code == 200, stopped.text
    state = stopped.json()
    assert state["pending"] is None
    assert state["tasks"][-1]["status"] == "cancelled"
    assert state["requests"][-1]["status"] == "cancelled"
    assert client.post(url + "/confirm", json=binding, headers=headers).status_code == 409
    assert lab.backends[sid].executions == 0
