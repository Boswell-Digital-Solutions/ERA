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


def wilson_interval(successes: int, total: int) -> dict[str, Any] | None:
    """95 percent Wilson score interval for a success rate. None when there are no tasks."""
    if total < 1:
        return None
    z = 1.959964
    rate = successes / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    margin = z * ((rate * (1 - rate) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return {
        "method": "wilson_score",
        "confidence": CONFIDENCE,
        "ci_low": round(max(0.0, centre - margin), 6),
        "ci_high": round(min(1.0, centre + margin), 6),
        "sample_count": total,
    }


def bootstrap_ratio_ci(numerators: list[float], successes: list[int]) -> dict[str, Any] | None:
    """Bootstrap interval for sum(numerators) / sum(successes), resampling whole tasks.

    None when there are too few tasks, or when a resample has no success (the ratio
    is undefined there). The seed comes from the task values.
    """
    count = len(numerators)
    if count < MIN_SAMPLES_FOR_CI or sum(successes) == 0:
        return None
    rng = random.Random(int(sha256_json([numerators, successes])[:16], 16))
    ratios: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        picks = [rng.randrange(count) for _ in range(count)]
        done = sum(successes[i] for i in picks)
        if done:
            ratios.append(sum(numerators[i] for i in picks) / done)
    if len(ratios) < BOOTSTRAP_RESAMPLES * 0.9:
        return None
    ratios.sort()
    low = ratios[int((1 - CONFIDENCE) / 2 * len(ratios))]
    high = ratios[int((1 + CONFIDENCE) / 2 * len(ratios)) - 1]
    return {
        "method": "bootstrap_ratio_percentile",
        "confidence": CONFIDENCE,
        "resamples": len(ratios),
        "ci_low": low,
        "ci_high": high,
        "sample_count": count,
    }
