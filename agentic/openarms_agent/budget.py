"""A local spending cap for the brain's Claude API calls.

Every response reports the tokens it used. This adds up their cost in a ledger file and refuses
further calls once the cap is reached, so a runaway loop or a long demo cannot quietly drain the
team's credit.

It only counts calls made through this code on this machine. Teammates' laptops, the voice
relay and anything else using the same key are not counted. The limit that covers all of those
is the spend limit in the Anthropic Console; set that too.

Cap: OPENARMS_API_CAP_USD in the environment or in agentic/.env (default 100).
"""
import json
import os
from pathlib import Path

AGENTIC = Path(__file__).resolve().parent.parent
LEDGER = AGENTIC.parent / "outputs" / "api_spend.json"  # outputs/ is ignored by git
DEFAULT_CAP_USD = 100.0
RESERVE_USD = 0.50  # stop this far short of the cap: one call's cost is only known after it returns

# US dollars per million tokens: (input, output, cache read, cache write)
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-opus-5": (5.00, 25.00, 0.50, 6.25),
    "claude-fable-5-2": (8.00, 40.00, 0.20, 10.00),
}
UNKNOWN_MODEL_PRICE = (10.00, 50.00, 1.00, 12.50)  # assume the worst for a model not listed above


class BudgetExceeded(RuntimeError):
    pass


def cost_usd(model: str, usage) -> float:
    """What one response cost. `usage` is the SDK's response.usage; missing fields count as zero."""
    inp, out, read, write = PRICES.get(model, UNKNOWN_MODEL_PRICE)

    def n(name: str) -> int:
        return int(getattr(usage, name, 0) or 0)

    return (n("input_tokens") * inp + n("output_tokens") * out
            + n("cache_read_input_tokens") * read + n("cache_creation_input_tokens") * write) / 1_000_000


def _cap_from_settings() -> float:
    raw = os.environ.get("OPENARMS_API_CAP_USD")
    env = AGENTIC / ".env"
    if raw is None and env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "OPENARMS_API_CAP_USD" and v.strip():
                raw = v.strip().strip("'\"")
    if raw is None:
        return DEFAULT_CAP_USD
    try:
        cap = float(raw)
    except ValueError:
        raise RuntimeError(f"OPENARMS_API_CAP_USD must be a number of dollars, not {raw!r}") from None
    if cap < 0:
        raise RuntimeError("OPENARMS_API_CAP_USD cannot be negative")
    return cap


class Budget:
    def __init__(self, cap_usd: float | None = None, ledger: Path | None = None) -> None:
        self.cap_usd = _cap_from_settings() if cap_usd is None else float(cap_usd)
        self.ledger = Path(ledger) if ledger else LEDGER
        self.last_usd = 0.0

    def _read(self) -> dict:
        if not self.ledger.exists():
            return {"spent_usd": 0.0, "calls": 0}
        try:
            data = json.loads(self.ledger.read_text())
            return {"spent_usd": float(data["spent_usd"]), "calls": int(data.get("calls", 0))}
        except (ValueError, KeyError, TypeError):
            # never guess low on a damaged ledger: stop until a person looks at it
            raise BudgetExceeded(f"The spend ledger {self.ledger} is unreadable; fix or delete it to continue.") from None

    @property
    def spent_usd(self) -> float:
        return self._read()["spent_usd"]

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)

    def check(self) -> None:
        """Call before every API request. Raises BudgetExceeded when the cap is reached."""
        spent = self.spent_usd
        if spent + RESERVE_USD >= self.cap_usd:
            raise BudgetExceeded(
                f"API spending cap reached: ${spent:.2f} used of ${self.cap_usd:.2f}. "
                "Raise OPENARMS_API_CAP_USD in agentic/.env to continue.")

    def record(self, model: str, usage) -> float:
        """Call after every API response. Returns what that response cost."""
        self.last_usd = cost_usd(model, usage)
        data = self._read()
        data["spent_usd"] = round(data["spent_usd"] + self.last_usd, 6)
        data["calls"] += 1
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ledger.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.replace(self.ledger)  # all-or-nothing, so a crash cannot leave half a ledger
        return self.last_usd

    def summary(self) -> str:
        return f"${self.spent_usd:.2f} of ${self.cap_usd:.2f} used"
