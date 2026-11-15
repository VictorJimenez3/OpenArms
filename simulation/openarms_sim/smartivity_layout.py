"""Procedural Smartivity layouts referenced to the main demo bench rulers."""
from dataclasses import dataclass
import math

import numpy as np
import yaml

from .config import load_bench, ruler_to_arm, setup_dir

MAX_SPREAD_MM = 18.0


@dataclass(frozen=True, slots=True)
class DemoLayout:
    seed: int
    spread_mm: float
    donor_arm_m: tuple[float, float]
    receiver_arm_m: tuple[float, float]
    donor_ruler_cm: tuple[float, float]
    receiver_ruler_cm: tuple[float, float]
    table_size_m: tuple[float, float]
    table_center_m: tuple[float, float]
    ruler_segments_arm_m: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    wrist_roll_deg: float
    lift_m: float

    def receipt(self) -> dict:
        return {
            "reference_setup": "demo",
            "seed": self.seed,
            "spread_mm_per_axis": self.spread_mm,
            "stations_ruler_cm": {"A": list(self.donor_ruler_cm), "C": list(self.receiver_ruler_cm)},
            "stations_arm_m": {"A": list(self.donor_arm_m), "C": list(self.receiver_arm_m)},
            "wrist_roll_deg": self.wrist_roll_deg,
            "lift_m": self.lift_m,
        }


def demo_layout(layout_seed: int = 0, spread_mm: float = 0.) -> DemoLayout:
    """Sample A and C independently around the main ruler coordinates.

    The span is a maximum displacement per axis, expressed in millimetres.
    Reachability and transfer are subsequently checked by the activity world.
    """
    if type(layout_seed) is not int or layout_seed < 0:
        raise ValueError("Layout seed must be a nonnegative integer.")
    if isinstance(spread_mm, bool) or not math.isfinite(spread_mm) or not 0 <= spread_mm <= MAX_SPREAD_MM:
        raise ValueError(f"Layout spread must be between 0 and {MAX_SPREAD_MM:g} mm.")
    bench = load_bench("demo")
    raw = yaml.safe_load((setup_dir("demo") / "bench.yaml").read_text(encoding="utf-8"))
    frame = raw["ruler_frame"]
    points = np.array([raw["stations"][station]["ruler"] for station in ("A", "C")], dtype=float)
    if spread_mm:
        points += np.random.default_rng(layout_seed).uniform(-spread_mm, spread_mm, (2, 2)) / 10.
    ruler_points = tuple(tuple(float(x) for x in point) for point in points)
    arm_points = tuple(ruler_to_arm(point, frame) for point in ruler_points)
    origin = ruler_to_arm((0, 0), frame)
    rulers = tuple((origin, ruler_to_arm(extent, frame)) for extent in ((30, 0), (0, 30)))
    return DemoLayout(layout_seed, float(spread_mm), *arm_points, *ruler_points, bench.table_size,
                      bench.table_center, rulers, bench.wrist_roll_deg, bench.lift)
