from agentic.openarms_agent.sim_preview import MuJoCoPreview


def state(**overrides):
    value = {
        "at": "HOME",
        "holding": None,
        "portions_left": {},
        "receiver_load": {},
        "armed": True,
        "point_holds": {"A": "block", "B": None},
    }
    value.update(overrides)
    return value


def plan():
    return {
        "plan_id": "p-1",
        "student_instruction": "move the block from A to B",
        "steps": [{"action": "move_block", "args": {"from": "A", "to": "B"}}],
    }


def good_preview(plan, **kwargs):
    assert kwargs == {"render": False, "use_cache": False, "setup": "block", "objects": {"block": "A"}}
    return {
        "setup": "block", "plan_id": plan["plan_id"],
        "ok": True,
        "objects": [{"name": "block", "at": "B", "started_at": "A", "moved": True}],
        "motion_seconds": 11.6,
        "issues": [],
        "warnings": ["poses are illustrative"],
        "cached": False,
    }


def test_headless_preview_reports_physics_evidence_and_expected_placement():
    evidence = MuJoCoPreview(good_preview)(
        plan(), state(), state(point_holds={"A": None, "B": "block"})
    )

    assert evidence["ok"] is True
    assert evidence["mode"] == "physics_simulation"
    assert evidence["engine"] == "mujoco"
    assert evidence["reported_placement"] == {"block": "B"}
    assert evidence["expected_placement"] == {"block": "B"}
    assert evidence["simulated_duration_s"] == 11.6
    assert evidence["reason"] is None


def test_placement_mismatch_is_a_preflight_failure():
    def wrong_preview(plan, **kwargs):
        return {"setup": "block", "plan_id": plan["plan_id"], "ok": True, "objects": [{"name": "block", "at": "A"}], "issues": []}

    evidence = MuJoCoPreview(wrong_preview)(
        plan(), state(), state(point_holds={"A": None, "B": "block"})
    )

    assert evidence["ok"] is False
    assert "placement" in evidence["reason"]


def test_simulator_block_is_preserved_as_reason():
    def blocked_preview(plan, **kwargs):
        return {
            "setup": "block", "plan_id": plan["plan_id"],
            "ok": False,
            "objects": [{"name": "block", "at": None}],
            "issues": [{"severity": "block", "code": "missed_grasp", "message": "gripper missed", "step": "pick(A)"}],
        }

    evidence = MuJoCoPreview(blocked_preview)(plan(), state(), state(point_holds={"A": None, "B": "block"}))

    assert evidence["ok"] is False
    assert evidence["reason"] == "gripper missed"
    assert evidence["issues"][0]["code"] == "missed_grasp"


def test_missing_optional_dependency_is_reported_without_importing_it():
    class Missing(MuJoCoPreview):
        @staticmethod
        def _load_preview():
            raise RuntimeError("MuJoCo simulator is unavailable")

    evidence = Missing()(plan(), state(), state(point_holds={"A": None, "B": "block"}))

    assert evidence["ok"] is False
    assert evidence["issues"][0]["code"] == "simulator_unavailable"
    assert "unavailable" in evidence["reason"]
