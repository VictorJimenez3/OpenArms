"""Predicts what a mixture looks like, and separately, whether it is safe.

The prediction side is swappable. Anything with a `predict(contents)` method
that returns an `Outcome` can replace `RuleTableChemistry`: register it in
`MODELS` and name it under `model:` in config/chemistry.yaml. A model that
computes pH from real volumes and concentrations would slot in here.

The safety side (`safety_issues`) is an explicit list on purpose and is not
part of the swappable model. A wrong colour prediction is harmless; a wrong
safety prediction is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Outcome:
    color: tuple[float, float, float]
    label: str  # e.g. "pink"
    observations: list[str] = field(default_factory=list)  # e.g. ["fizzing"]

    def describe(self) -> str:
        return " with ".join([self.label, *self.observations]) if self.observations else self.label


class ChemistryModel(Protocol):
    def predict(self, contents: dict[str, float]) -> Outcome: ...


class RuleTableChemistry:
    """Colour from a lookup: indicator colour by (acid portions - base portions)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.substances = cfg["substances"]
        self.scale = sorted(cfg["indicator_scale"], key=lambda r: -r["min"])

    def _kinds(self, contents: dict[str, float]) -> dict[str, float]:
        """Total strength-weighted portions per kind (acid, base, ...)."""
        totals: dict[str, float] = {}
        for name, amount in contents.items():
            if amount <= 0:
                continue
            sub = self.substances.get(name, {"kind": "unknown"})
            weight = sub.get("strength", 1) if sub["kind"] in ("acid", "base") else 1
            totals[sub["kind"]] = totals.get(sub["kind"], 0) + amount * weight
        return totals

    def predict(self, contents: dict[str, float]) -> Outcome:
        kinds = self._kinds(contents)
        observations = [
            rule["text"] for rule in self.cfg.get("observations", []) if all(k in kinds for k in rule["when_all"])
        ]
        if not kinds:
            return Outcome((0.9, 0.9, 0.9), "empty")
        if "indicator" in kinds:
            net = kinds.get("acid", 0) - kinds.get("base", 0)
            row = next(r for r in self.scale if net >= r["min"])
            return Outcome(tuple(row["color"]), row["label"], observations)
        plain = self.cfg["plain_colors"]
        dominant = max((k for k in kinds if k in plain), key=lambda k: kinds[k], default="neutral")
        return Outcome(tuple(plain[dominant]), "clear", observations)


MODELS = {"rule_table": RuleTableChemistry}


def load_model(cfg: dict) -> ChemistryModel:
    name = cfg.get("model", "rule_table")
    if name not in MODELS:
        raise ValueError(f"unknown chemistry model {name!r}; known: {sorted(MODELS)}")
    return MODELS[name](cfg)


def display_name(cfg: dict, substance: str) -> str:
    return cfg["substances"].get(substance, {}).get("name", substance)


def safety_issues(cfg: dict, contents: dict[str, float]) -> list[str]:
    """Reasons this mixture must not be made on the real bench. Empty means allowed."""
    present = {name for name, amount in contents.items() if amount > 0}
    issues = []
    for name in sorted(present):
        if name not in cfg["substances"]:
            issues.append(f"{name} is not a known substance")
        elif name not in cfg["real_bench"]:
            issues.append(f"{display_name(cfg, name)} is simulation-only and not allowed on the real bench")
    for hazard in cfg.get("hazards", []):
        if all(m in present for m in hazard["mix"]):
            issues.append(hazard["reason"])
    return issues
