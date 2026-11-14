"""Paid smoke test for the brain (~3-4 API calls): vague instruction, then a clear one with a yes."""
from agentic.openarms_agent.brain import Brain


def main(client=None) -> None:
    b = Brain("smoke-vague", client=client)
    b.session.predicted = True  # skip pre-lab so the check is about planning
    r = b.handle_turn("t1", "do the vinegar one")
    print("vague:", r["status"], "|", r["text"])
    assert r["status"] == "reply" and r["plan"] is None, "vague instruction should get a question, not a plan"

    b = Brain("smoke-clear", client=client)
    b.session.predicted = True
    r = b.handle_turn("t1", "add one portion of A to C")
    print("clear:", r["status"], "|", r["text"])
    if r["status"] != "awaiting_teacher":
        r = b.handle_turn("t2", "yes, send it")
        print("yes:", r["status"], "|", r["text"])
    assert r["status"] == "awaiting_teacher" and r["plan"], "clear instruction plus yes should end awaiting_teacher"
    print("plan:", r["plan"])
    print("OK")


if __name__ == "__main__":
    main()
