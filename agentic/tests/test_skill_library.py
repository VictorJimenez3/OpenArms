import json

import pytest

from agentic.openarms_agent.skill_library import SkillLibrary


def test_promote_resolve_and_reload_preserves_versions(tmp_path):
    path = tmp_path / "skills.json"
    first = [{"action": "move_block", "args": {"from": "A", "to": "B"}}]
    second = [{"action": "move_block", "args": {"from": "A", "to": "C"}}]

    library = SkillLibrary(path)
    assert library.resolve(" Move   the block from A to B ", scope="bench-1") is None
    assert library.promote("Move   the block from A to B", first, scope="Bench-1") == 1
    assert library.promote("move the block from a to b", second, scope="bench-1") == 2
    assert library.resolve("move the block from A to B", scope="BENCH-1") == second

    raw = json.loads(path.read_text())
    assert raw["skills"]["bench-1"]["move the block from a to b"]["active_version"] == 2
    assert [v["version"] for v in raw["skills"]["bench-1"]["move the block from a to b"]["versions"]] == [1, 2]

    reloaded = SkillLibrary(path)
    result = reloaded.resolve("move the block from a to b", scope="bench-1")
    assert result == second
    result[0]["args"]["to"] = "D"
    assert reloaded.resolve("move the block from a to b", scope="bench-1") == second


def test_resolution_is_exact_and_does_not_leak_parameters(tmp_path):
    library = SkillLibrary(tmp_path / "skills.json")
    steps = [{"action": "move_block", "args": {"from": "A", "to": "B"}}]
    library.promote("Move the block from A to B", steps, scope="bench-1")

    assert library.resolve("move the block from A to C", scope="bench-1") is None
    assert library.resolve("move the block from A to B, then wait", scope="bench-1") is None
    assert library.resolve("move the block from A to B", scope="bench-2") is None


def test_same_phrase_is_isolated_by_scope(tmp_path):
    library = SkillLibrary(tmp_path / "skills.json")
    a_to_b = [{"action": "move_block", "args": {"from": "A", "to": "B"}}]
    c_to_b = [{"action": "move_block", "args": {"from": "C", "to": "B"}}]
    library.promote("move the block", a_to_b, scope="stations:a,b")
    library.promote("move the block", c_to_b, scope="stations:c,b")
    assert library.resolve("move the block", scope="stations:a,b") == a_to_b
    assert library.resolve("move the block", scope="stations:c,b") == c_to_b


@pytest.mark.parametrize(
    "steps",
    [
        [{"action": "not_a_catalog_action", "args": {}}],
        [{"action": "move_block", "args": {"from": "A", "to": "B", "speed": 1}}],
        [{"action": "wait", "args": {"seconds": 31}}],
    ],
)
def test_promote_rejects_invalid_or_unsafe_steps(tmp_path, steps):
    with pytest.raises(ValueError):
        SkillLibrary(tmp_path / "skills.json").promote("unsafe", steps)


def test_promote_rejects_empty_or_too_many_steps(tmp_path):
    library = SkillLibrary(tmp_path / "skills.json")
    with pytest.raises(ValueError):
        library.promote("empty", [])
    too_many = [{"action": "wait", "args": {"seconds": 1}} for _ in range(7)]
    with pytest.raises(ValueError):
        library.promote("long", too_many)


def test_malformed_store_is_reported(tmp_path):
    path = tmp_path / "skills.json"
    path.write_text('{"skills": []}')
    with pytest.raises(ValueError, match="skills"):
        SkillLibrary(path).resolve("anything")


def test_promote_rejects_oversized_phrase_and_scope_before_catalog(tmp_path):
    library = SkillLibrary(tmp_path / "skills.json")
    steps = [{"action": "move_block", "args": {"from": "A", "to": "B"}}]
    with pytest.raises(ValueError, match="240"):
        library.promote("x" * 241, steps)
    with pytest.raises(ValueError, match="240"):
        library.promote("short", steps, scope="x" * 241)
