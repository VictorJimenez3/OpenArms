"""The brain: one student turn in, one TurnReply out, via Claude tool use."""
import json
import os
import re
from pathlib import Path
from typing import Optional

from .mock_arm import MockArm
from .notebook import Notebook
from .prompting import render_system_prompt
from .tools import TOOLS, Session, dispatch
from .types import ArmPort, ExecutionResult, Station, TurnReply

MODEL = "claude-sonnet-5-5"
MAX_TOOL_ROUNDS = 10
AGENTIC = Path(__file__).resolve().parent.parent
STOP_WORDS = re.compile(r"\b(stop|cancel)\b", re.IGNORECASE)
DEFAULT_OBJECTIVE = "Test how each sample changes the color of the purple cabbage indicator."


def _load_key() -> str:
    env = AGENTIC / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "ANTHROPIC_API_KEY" and v.strip():
                os.environ.setdefault("ANTHROPIC_API_KEY", v.strip().strip("'\""))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not found: put ANTHROPIC_API_KEY=... in agentic/.env")
    return os.environ["ANTHROPIC_API_KEY"]


class Brain:
    def __init__(self, session_id: str, stations: Optional[dict[str, Station]] = None, arm: Optional[ArmPort] = None,
                 objective: str = DEFAULT_OBJECTIVE, client=None):
        if stations is None:
            stations = json.loads((AGENTIC / "contracts" / "stations.example.json").read_text())
        self.session = Session(session_id, stations, arm if arm is not None else MockArm(), Notebook(session_id))
        self.objective, self._client = objective, client
        self.messages: list[dict] = []
        self._notes: list[str] = []  # lab events waiting to ride along with the next student turn

    @property
    def client(self):
        if self._client is None:  # lazy, so stop words and notify work without a key
            import anthropic
            self._client = anthropic.Anthropic(api_key=_load_key())
        return self._client

    def _reply(self, turn_id: str, text: str, status: str, plan=None) -> TurnReply:
        stage = "experiment" if self.session.predicted else "pre_lab"
        return {"turn_id": turn_id, "text": text, "status": status, "plan": plan, "lab_stage": stage}

    def handle_turn(self, turn_id: str, text: str) -> TurnReply:
        s = self.session
        if STOP_WORDS.search(text):
            # the runner reads stop_requested via should_stop and calls arm.stop(); MockArm.stop() is permanent
            s.stop_requested, s.pending_plan = True, None
            s.notebook.add("result", status="stop_requested", text=text)
            self._notes.append("[lab] The student asked to stop. The arm is holding still and any pending plan was cancelled.")
            return self._reply(turn_id, "Stopping. The arm will finish its current motion and hold still.", "stop_requested")

        # stop_requested clears only when a new plan is submitted; pending_plan survives small talk
        self._add_user("\n".join(self._notes + [text]))
        self._notes = []
        for _ in range(MAX_TOOL_ROUNDS):
            resp = self.client.messages.create(
                model=MODEL, max_tokens=16000, tools=TOOLS, messages=self.messages,
                system=render_system_prompt(s.stations, s.arm.state(), self.objective))
            # append the whole content so thinking blocks go back unchanged
            self.messages.append({"role": "assistant", "content": resp.content})
            cut = resp.stop_reason != "tool_use"  # e.g. max_tokens: the tool input may be incomplete
            results = [self._run_tool(b, cut) for b in resp.content if b.type == "tool_use"]
            if results:  # every tool_use needs a tool_result, even on max_tokens, or the next call 400s
                self.messages.append({"role": "user", "content": results})
            if resp.stop_reason != "tool_use":
                break
        else:
            return self._reply(turn_id, "Sorry, I got stuck. Could you say that again?", "reply")

        reply = " ".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason == "refusal" or not reply:
            reply = reply or "Sorry, I can't help with that. What would you like the arm to do?"
        if s.help_requested:
            return self._reply(turn_id, reply, "help_requested")
        if s.pending_plan is not None:
            return self._reply(turn_id, reply, "awaiting_teacher", s.pending_plan)
        return self._reply(turn_id, reply, "reply")

    def _run_tool(self, b, cut: bool = False) -> dict:
        if cut:
            return {"type": "tool_result", "tool_use_id": b.id, "content": "reply was cut off; tool not run", "is_error": True}
        try:
            return {"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(dispatch(b.name, b.input, self.session))}
        except Exception as e:  # a bad tool input goes back to the model, not up the stack
            return {"type": "tool_result", "tool_use_id": b.id, "content": f"{type(e).__name__}: {e}", "is_error": True}

    def _add_user(self, text: str) -> None:
        last = self.messages[-1] if self.messages else None
        if last and last["role"] == "user":  # history ended on tool results; merge to keep roles alternating
            prev = last["content"]  # a string if the last API call failed after we added it
            prev = [{"type": "text", "text": prev}] if isinstance(prev, str) else list(prev)
            last["content"] = prev + [{"type": "text", "text": text}]
        else:
            self.messages.append({"role": "user", "content": text})

    def notify(self, result: ExecutionResult) -> TurnReply:
        s = self.session
        s.pending_plan = None
        s.notebook.add("result", **result)
        s.notebook.save()
        status, step, reason = result["status"], result.get("failed_step"), result.get("reason")
        if status == "executed":
            text = "The arm finished the steps. Take a look. What do you see?"
        elif status == "teacher_rejected":
            text = f"Your teacher did not approve the plan{': ' + reason.rstrip('.') if reason else ''}. What would you like to do?"
        elif status in ("failed", "stopped"):
            text = f"The arm stopped at {step or 'an unknown step'}{': ' + reason.rstrip('.') if reason else ''}. What would you like to do next?"
        else:
            text = f"The plan ended with status {status}{': ' + reason.rstrip('.') if reason else ''}. What would you like to do?"
        self._notes.append(f"[lab] Run result for {result['plan_id']}: {json.dumps(result)}. You told the student: {text}")
        return self._reply(f"notify-{result['plan_id']}", text, "reply")
