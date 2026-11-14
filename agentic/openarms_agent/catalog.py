"""Plan actions the brain may use, and their expansion into arm steps."""
from .types import Plan, Step

ACTIONS = {"add_sample": {"source", "into", "portions"}, "wait": {"seconds"}, "look": {"station"}}


def _check(action, args) -> None:
    if not isinstance(action, str):
        raise ValueError("Each step's action must be a name like add_sample.")
    if not isinstance(args, dict):
        raise ValueError("Each step's args must be an object.")
    if action not in ACTIONS:
        raise ValueError(f"'{action}' is not a plan action; use add_sample, wait or look.")
    extra = set(args) - ACTIONS[action]
    if extra:
        raise ValueError(f"{action} does not take {', '.join(sorted(extra))}.")
    if action == "add_sample":
        for key in ("source", "into"):
            if not isinstance(args.get(key), str) or not args[key]:
                raise ValueError(f"add_sample needs a station name for {key}.")
        p = args.get("portions", 1)
        if type(p) is not int or not 1 <= p <= 10:
            raise ValueError("add_sample portions must be a whole number from 1 to 10.")
    elif action == "wait":
        s = args.get("seconds")
        if type(s) not in (int, float) or not 1 <= s <= 30:
            raise ValueError("wait seconds must be a number from 1 to 30.")
    elif not isinstance(args.get("station"), str) or not args["station"]:
        raise ValueError("look needs a station name.")


def expand(plan: Plan) -> list[Step]:
    steps: list[Step] = []
    items = plan.get("steps") or []
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ValueError("steps must be a list of {action, args} objects.")
    for item in items:
        action, args = item.get("action"), item.get("args", {})
        _check(action, args)
        if action == "add_sample":
            src, into = args["source"], args["into"]
            for _ in range(args.get("portions", 1)):
                steps += [{"action": "pick", "args": {"station": src}},
                          {"action": "pour", "args": {"into": into}},
                          {"action": "return_cup", "args": {"station": src}}]
            steps.append({"action": "home", "args": {}})
        else:
            steps.append({"action": action, "args": dict(args)})
    return steps
