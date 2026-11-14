# agentic/

> **Scope correction — demo-speed-v1:** [Architecture](../docs/ARCHITECTURE.md) defines the target. The lesson/prediction/quiz sequence below describes existing or historical behavior, not a mandatory student workflow. Students choose individual physical actions. Preserve existing authorization and STOP while integrating the corrected flow; mock/simulation success is not physical demo completion.

The agent harness: the LLM "brain" turns a student's words into a short plan, local code checks it, the teacher approves it, and the arm runs it. Design: [research/duc/harness.md](../research/duc/harness.md). Owner: Duc.

## Setup

```bash
conda create -y -n openarms python=3.12
conda activate openarms
pip install -r agentic/requirements.txt
echo "ANTHROPIC_API_KEY=..." > agentic/.env   # ignored by git
```

Run everything from the repo root as modules, for example `python -m agentic.scripts.check_validator`.

## Layout

| File | What it does | Lane |
|---|---|---|
| `contracts/*.example.json` | One example of each shared shape; the team agrees on these in `docs/INTERFACES.md` | master |
| `openarms_agent/types.py` | Key names for those shapes, the `ArmPort` protocol, `ArmError` | master |
| `openarms_agent/catalog.py` | Plan actions (`add_sample`, `wait`, `look`) and `expand()` into arm steps | core |
| `openarms_agent/validator.py` | `validate(plan, state, stations)`: fixed rules, one readable reason | core |
| `openarms_agent/mock_arm.py` | Fake `ArmPort` for development | core |
| `openarms_agent/runner.py` | Runs approved steps on an `ArmPort`; stops on error or STOP; never retries | core |
| `openarms_agent/notebook.py` | Session log to `outputs/sessions/<id>.json` | core |
| `prompts/brain_system.md`, `openarms_agent/prompting.py` | The brain's system prompt | brain |
| `openarms_agent/tools.py`, `openarms_agent/brain.py` | Claude tools and the turn loop | brain |
| `relay_adapter.py`, `server.py`, `preview.py` | Links to the voice relay, teacher UI and sim | api (later) |

The real `ArmPort` (saved-pose replay on the SO-101) is drafted in `firmware/openarms_executor/` for Joseph to review.

Files marked "M0 stub" return canned values so lanes can run before the real code lands.
