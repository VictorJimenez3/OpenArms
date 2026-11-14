"""Renders the brain's system prompt from agentic/prompts/brain_system.md."""
import json
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "brain_system.md"


def _stations_table(stations: dict) -> str:
    rows = []
    for name, st in stations.items():
        amount = (f"{st['portions']} portions" if st.get("kind") == "source" and "portions" in st
                  else f"room for {st['capacity']} portions" if "capacity" in st else "")
        rows.append(f"- {name}: {st.get('kind', '?')}, holds {st.get('contents', 'unknown')}" + (f", {amount}" if amount else ""))
    return "\n".join(rows)


def render_system_prompt(stations: dict, arm_state: dict, objective: str) -> str:
    return (TEMPLATE.read_text()
            .replace("{{objective}}", objective)
            .replace("{{stations_table}}", _stations_table(stations))
            .replace("{{arm_state}}", json.dumps(arm_state)))
