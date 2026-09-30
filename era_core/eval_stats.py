"""Bounded uncertainty for BDS-ERA-EVAL-v0.1 (WP08).

The bootstrap is deterministic. The seed comes from the sample values, so the same
samples always give the same interval. ERA can rebuild it from the artifacts.
"""

from __future__ import annotations

import random
import statistics
from typing import Any

from era_core.hashing import sha256_json

BOOTSTRAP_RESAMPLES = 1000
MIN_SAMPLES_FOR_CI = 5
CONFIDENCE = 0.95
METHOD = "bootstrap_median_percentile"


def bootstrap_median_ci(values: list[float]) -> dict[str, Any] | None:
    """Return a 95 percent percentile bootstrap interval for the median, or None.

    None means too few samples for a bounded claim. The caller records the reason.
    """
    if len(values) < MIN_SAMPLES_FOR_CI:
        return None
    seed = int(sha256_json(sorted(values))[:16], 16)
    rng = random.Random(seed)
    count = len(values)
    medians = sorted(
        statistics.median(rng.choices(values, k=count)) for _ in range(BOOTSTRAP_RESAMPLES)
    )
    low = medians[int((1 - CONFIDENCE) / 2 * BOOTSTRAP_RESAMPLES)]
    high = medians[int((1 + CONFIDENCE) / 2 * BOOTSTRAP_RESAMPLES) - 1]
    return {
        "method": METHOD,
        "confidence": CONFIDENCE,
        "resamples": BOOTSTRAP_RESAMPLES,
        "ci_low": low,
        "ci_high": high,
        "sample_count": count,
    }


def intervals_overlap(first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool | None:
    """True when the intervals overlap. None when either one is missing."""
    if first is None or second is None:
        return None
    return first["ci_low"] <= second["ci_high"] and second["ci_low"] <= first["ci_high"]
