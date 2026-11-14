"""Renders the brain's system prompt from agentic/prompts/brain_system.md."""
import json
from pathlib import Path

from .validator import pose_names

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "brain_system.md"


def _stations_table(stations: dict, arm_state: dict | None = None) -> str:
    rows = []
    now = (arm_state or {}).get("point_holds")  # live positions once the session has an arm state
    for name, st in stations.items():
        if st.get("kind") == "point":
            thing = now.get(name) if now is not None else st.get("holds")
            rows.append(f"- {name}: point, " + (f"the {thing} is here" if thing else "empty"))
            continue
        amount = (f"{st['portions']} portions" if st.get("kind") == "source" and "portions" in st
                  else f"room for {st['capacity']} portions" if "capacity" in st else "")
        rows.append(f"- {name}: {st.get('kind', '?')}, holds {st.get('contents', 'unknown')}" + (f", {amount}" if amount else ""))
    return "\n".join(rows)


def render_system_prompt(stations: dict, arm_state: dict, objective: str) -> str:
    return (TEMPLATE.read_text()
            .replace("{{objective}}", objective)
            .replace("{{stations_table}}", _stations_table(stations, arm_state))
            .replace("{{poses}}", ", ".join(arm_state.get("poses") or pose_names(stations)))
            .replace("{{arm_state}}", json.dumps(arm_state)))
