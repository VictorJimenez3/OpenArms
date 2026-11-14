# Proposed Mac-side asynchronous dialogue adapter

The actual agent is absent from this repository. `dialogue.py` declares the small boundary used by this mock:

```python
@dataclass(frozen=True)
class Context:
    session_id: str
    turn_id: str

@dataclass(frozen=True)
class Reply:
    text: str
    lab_stage: str

class DialogueAdapter(Protocol):
    async def respond(self, context: Context, student_text: str | None) -> Reply: ...
    async def close(self) -> None: ...
```

`handler_factory(..., adapter_factory=MockDialogue)` makes a fresh adapter for every connection. Calls within that session are sequential. `student_text=None` requests the opening prompt; otherwise it is a nonempty recognized transcript, capped at 4,096 characters. Context IDs are stable across that turn's transcript, reply, audio acknowledgement and logs. The adapter returns nonempty speakable text, at most 4,096 characters, and a descriptive stage such as `prediction`, `preview`, `confirmation`, `result`, or `reflection`. Transport, VAD, recognition, TTS, and playback acknowledgement remain the relay's responsibility.

The method must yield to asyncio during slow work. Cancellation on end/disconnect/shutdown must propagate and release resources. `close()` should be idempotent and promptly release per-session resources; relay bounds it to five seconds. Any adapter exception ends the session with a generic fatal error and a detailed private log entry; there is no automatic retry that could repeat an action. An adapter must not reuse another session's pending confirmation or state.

## One concrete mock contract

These are Python call/result examples, not additional phone messages:

```text
respond(Context("s-A", "t-1"), None)
  -> Reply("This is a simulation. Predict ...", "prediction")

respond(Context("s-A", "t-2"), "The block will reach the target.")
  -> Reply("Preview: ... No hardware will move. Say confirm ... or cancel.", "preview")

respond(Context("s-A", "t-3"), "do not confirm")
  -> Reply("Please say confirm ... or cancel ...", "confirmation")

respond(Context("s-A", "t-4"), "Confirm.")
  -> Reply("Simulated result: the block reached the target. No hardware moved. How does this compare with your prediction?", "result")

respond(Context("s-A", "t-5"), "That matched my prediction.")
  -> Reply("Thank you for reflecting. For another simulated trial, predict ...", "reflection")
```

At the preview step, `cancel` instead returns a cancelled simulation and reflection prompt. No physical or production operation exists in either branch.

## Future handoff requirements

A spoken confirmation is a conversational event only. A future real adapter must use the team's separately agreed preview, approval, execution and result rules. `lab_stage`, an ASR transcript, `played`, and any phone UI state are not execution authorization. This boundary has no execution method or hardware transport and is not enough to design a safe real action API. Before integration, agree with the agent owner on one example including proposal identity/version, approval binding, cancellation behavior, action limits and result/error semantics, then record that agreement in the shared `docs/INTERFACES.md` and issue #2. Keep this mock independently runnable and tested.
