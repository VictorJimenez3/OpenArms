# Lane: brain (branch duc/brain)

The LLM loop. Estimate: 5 tickets × 8–12 min, plus Duc's review between runs = **~60–90 min**. Cap **7**. **Attended `once.sh` only**: B3 and B5 spend API credits.
Call core's functions (`catalog`, `validator`, `notebook`) by their `types.py` signatures even before core has landed. Until core lands, the M0 stubs return canned values, so your Checks still run.

- [ ] **B1 System prompt.**
  - What: port Part D of `research/duc/harness.md` to the three-action catalog (`add_sample`, `wait`, `look`). Stations include their contents. Write `render_system_prompt(stations, arm_state, objective) -> str`.
  - Files you own: `agentic/prompts/brain_system.md`, `agentic/openarms_agent/prompting.py`
  - Done when: no `{{...}}` placeholders are left after rendering; the prompt says "portions", never mL; the hard rules from Part D are kept.
  - Check: `python -c "from agentic.openarms_agent.prompting import render_system_prompt as r; s=r({'A':'vinegar'},{'at':'HOME'},'test'); assert '{{' not in s; print(len(s))"`
- [ ] **B2 Tool definitions.**
  - What: Claude tool schemas and a dispatcher for `submit_plan`, `record_prediction`, `record_observation`, `look`, `request_help`, `get_notebook`. `submit_plan` calls `validator.validate` and returns the rejection reason or `awaiting_teacher`. It never runs the arm.
  - Files you own: `agentic/openarms_agent/tools.py`
  - Done when: `TOOLS` is a valid list for the Messages API, and `dispatch(name, input, session)` returns a JSON-serializable result for each tool.
  - Check: `python -c "import json; from agentic.openarms_agent.tools import TOOLS; print(json.dumps([t['name'] for t in TOOLS]))"`
- [ ] **B3 Brain turn loop.**
  - What: `Brain(session_id).handle_turn(turn_id, text) -> TurnReply`. One student turn = one Messages API call with tool use, looping only through tool calls until the final reply. Keeps the full conversation history. Model `claude-sonnet-5-5`; key from `agentic/.env`.
  - Files you own: `agentic/openarms_agent/brain.py`
  - Done when: a vague instruction gets a clarifying question; a clear one ends with a plan in `awaiting_teacher`.
  - Check (paid, ~2 calls): `python -m agentic.scripts.brain_smoke` (you own this script)
- [ ] **B4 Stop words and execution feedback.**
  - What: (a) `handle_turn` checks for stop, wait or cancel *before* any LLM call and returns a fixed reply with `status='stop_requested'`; (b) `Brain.notify(result: ExecutionResult) -> TurnReply` tells the student what happened in one short line and asks what they see.
  - Files you own: `agentic/openarms_agent/brain.py`
  - Done when: "stop!" never reaches the model; `notify` on a failed result names the failed step.
  - Check: `python -c "from agentic.openarms_agent.brain import Brain; print(Brain('s').handle_turn('t1','stop!'))"`
- [ ] **B5 Terminal REPL.**
  - What: `agentic/scripts/brain_repl.py`. Type as the student; on `awaiting_teacher` it asks y/n as the teacher, runs `runner.run` on `MockArm`, then calls `notify`.
  - Files you own: `agentic/scripts/brain_repl.py`
  - Done when: a whole prediction → plan → approve → run → observation session works in the terminal.
  - Check (paid): run it by hand for one experiment.
