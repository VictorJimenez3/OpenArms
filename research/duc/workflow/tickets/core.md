# Lane: core (branch duc/core)

Pure Python, no network, no hardware. Estimate: 5 tickets × 5–10 min = **~45–75 min**. Cap **7**. Run `once.sh` twice; if both commits look right, `afk.sh 5`.
Types and signatures come from `agentic/openarms_agent/types.py` (read-only for you).

- [ ] **C1 Action catalog.**
  - What: the three brain actions (`add_sample(source, into, portions=1)`, `wait(seconds)`, `look(station)`) with argument checks, and `expand(plan) -> list[Step]`, which turns `add_sample` into `pick`, `pour` × portions, `return_cup`, `home`.
  - Files you own: `agentic/openarms_agent/catalog.py`
  - Done when: unknown actions or bad arguments raise `ValueError` with a short readable reason, and expanding one `add_sample(A, C, 2)` gives 5 steps.
  - Check: `python -c "from agentic.openarms_agent import catalog; print(catalog.expand({'plan_id':'p1','student_instruction':'x','steps':[{'action':'add_sample','args':{'source':'A','into':'C','portions':2}}]}))"`
- [ ] **C2 Validator.**
  - What: `validate(plan, state) -> ValidationResult`. It walks the expanded plan against the arm state and rejects: unknown action, bad argument, more than 6 brain steps, an empty source, a receiver over capacity, or not ending at HOME with an empty gripper. On success it returns the predicted end state.
  - Files you own: `agentic/openarms_agent/validator.py`
  - Done when: each rejection gives one readable sentence, and a valid plan returns `ok=True` with updated `portions_left` and `receiver_load`.
  - Check: `python -m agentic.scripts.check_validator` (you own this script; it prints one accepted and three rejected example plans)
- [ ] **C3 Mock arm.**
  - What: `MockArm`, implementing `ArmPort`. Each step sleeps ~0.5 s and updates state. Options make it fail at a named step, and `stop()` takes effect between steps.
  - Files you own: `agentic/openarms_agent/mock_arm.py`
  - Done when: running the expanded C1 plan through it changes the state just as the validator predicted.
  - Check: `python -c "from agentic.openarms_agent.mock_arm import MockArm; a=MockArm(); a.run_step('pick',{'station':'A'}); print(a.state())"`
- [ ] **C4 Plan runner.**
  - What: `run(plan, arm: ArmPort, should_stop=lambda: False) -> ExecutionResult`. It runs the expanded steps in order and stops at the first `ArmError` or when stopped, reporting which step failed. It never retries.
  - Files you own: `agentic/openarms_agent/runner.py`
  - Done when: a clean run returns `executed`, a failure injected at `pour` returns `failed` with `failed_step='pour'`, and a stop returns `stopped`.
  - Check: `python -m agentic.scripts.check_runner` (you own this script)
- [ ] **C5 Session notebook.**
  - What: `Notebook(session_id)` with `add(kind, **data)` (kinds: prediction, plan, result, observation, help), `entries()`, `save()` to `outputs/sessions/<id>.json`, and `as_text()` for the brain's context.
  - Files you own: `agentic/openarms_agent/notebook.py`
  - Done when: save, then reload, round-trips; `as_text()` is short and readable.
  - Check: `python -c "from agentic.openarms_agent.notebook import Notebook; n=Notebook('s-test'); n.add('prediction', text='turns pink'); print(n.as_text()); n.save()"`
