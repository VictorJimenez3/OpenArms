"""Self-check for move_to on FakeRobot: exact end, no jumps, stop holds."""
from .motion import FakeRobot, move_to

target = {"shoulder_pan.pos": 40.0, "elbow_flex.pos": -25.0}
r = FakeRobot({"shoulder_pan.pos": -20.0, "wrist_roll.pos": 7.0})
seconds, hz = 0.2, 30
assert move_to(r, target, seconds, hz)
assert all(r.pos[k] == v for k, v in target.items()), r.pos
assert r.pos["wrist_roll.pos"] == 7.0 and r.pos["gripper.pos"] == 0.0

prev = {"shoulder_pan.pos": -20.0, "elbow_flex.pos": 0.0}
limit = {k: abs(target[k] - prev[k]) / (seconds * hz) + 1e-9 for k in target}
for cmd in r.sent:
    for k, v in cmd.items():
        assert abs(v - prev[k]) <= limit[k], (k, v, prev[k])
        prev[k] = v

r2, calls = FakeRobot(), []
stopped = not move_to(r2, {"shoulder_pan.pos": 90.0}, seconds, hz, should_stop=lambda: calls.append(1) or len(calls) > 3)
assert stopped and 0 < r2.pos["shoulder_pan.pos"] < 90.0, r2.pos
print(f"check_motion ok: {len(r.sent)} steps, exact end, max step within limit, stop held at {r2.pos['shoulder_pan.pos']:.1f}")
