"""Run the text-to-plan harness against a local simulated bench."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from agentic.openarms_agent.cold_planner import MODEL, ClaudePlanner
from agentic.openarms_agent.mock_arm import MockArm
from agentic.openarms_agent.skill_harness import SkillHarness
from agentic.openarms_agent.skill_library import SkillLibrary
from agentic.openarms_agent.sim_preview import MuJoCoPreview

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", choices=("block", "mandarin", "liquid"), default="block")
    parser.add_argument("--session", default=None, help="Reuse a session name to load its notebook.")
    parser.add_argument("--data", type=Path, default=Path("outputs/skill-harness"))
    parser.add_argument("--planner", choices=("offline", "claude"), default="offline")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--mujoco", action="store_true", help="Require a headless block preflight.")
    args = parser.parse_args()
    if args.mujoco and args.bench != "block":
        parser.error("--mujoco requires --bench block.")

    name = "stations.example.json" if args.bench == "liquid" else "stations.block.example.json"
    stations = json.loads((CONTRACTS / name).read_text())
    if args.bench == "mandarin":
        stations["A"]["holds"] = "mandarin"
    harness = SkillHarness(
        session_id=args.session or uuid4().hex, stations=stations, arm=MockArm(stations, step_seconds=0),
        planner=ClaudePlanner(model=args.model) if args.planner == "claude" else None,
        preview=MuJoCoPreview() if args.mujoco else None,
        library=SkillLibrary(args.data / "skills.json"), journal_dir=args.data / "sessions",
    )
    print("Mock bench. Waits and state are modeled. Commands: confirm ID, promote ID, predict TEXT, observe TEXT, history, stop, quit.")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            return
        if line.casefold() == "quit":
            return
        command, _, value = line.partition(" ")
        try:
            match command.casefold():
                case "confirm":
                    reply = harness.confirm(value)
                case "promote":
                    reply = {"version": harness.promote(value)}
                case "predict":
                    harness.record_prediction(value)
                    reply = {"saved": True}
                case "observe":
                    harness.record_observation(value, source="student")
                    reply = {"saved": True, "source": "student"}
                case "history":
                    reply = {"entries": harness.history()}
                case _:
                    reply = harness.propose(line)
        except (ValueError, OSError) as exc:
            reply = {"status": "error", "reason": str(exc)}
        print(json.dumps(reply))


if __name__ == "__main__":
    main()
