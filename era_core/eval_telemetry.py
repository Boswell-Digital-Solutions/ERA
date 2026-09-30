"""Inference telemetry ingestion for BDS-ERA-EVAL-v0.1 (WP07).

ERA does not measure an inference engine. An external tool writes an
``InferenceTelemetry.v1`` file into the target tree. ERA reads it, summarizes each
declared metric, and adds the results to the ``MetricVector.v1``. ERA keeps every
metric on its own row. It never combines them into one score.

File format::

    {
      "schema_version": "InferenceTelemetry.v1",
      "measurement_scope": "local_engine_client",
      "samples": {
        "ttft_ms": [..], "tpot_ms": [..], "itl_ms": [..],
        "output_tokens_per_second": [..], "throughput_rps": [..],
        "ram_mb": [..], "vram_mb": [..],
        "context_tokens": [..], "output_tokens": [..]
      }
    }

Manifest block (inside ``evaluation``)::

    "telemetry_policy": {
      "telemetry_results_path": "telemetry/results.json",
      "percentile_metrics": ["ttft_ms"],
      "p95_min_samples": 20, "p99_min_samples": 100
    }
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from era_core.eval_stats import MIN_SAMPLES_FOR_CI, bootstrap_median_ci
from era_core.hashing import sha256_path

TELEMETRY_SCHEMA = "InferenceTelemetry.v1"

# Known metric names, their unit, and the scope word that goes into the vector.
KNOWN_METRICS: dict[str, str] = {
    "ttft_ms": "ms",
    "tpot_ms": "ms",
    "itl_ms": "ms",
    "output_tokens_per_second": "tokens/s",
    "throughput_rps": "requests/s",
    "ram_mb": "MB",
    "vram_mb": "MB",
    "context_tokens": "tokens",
    "output_tokens": "tokens",
    "energy_joules": "J",
    "energy_per_token_j": "J/token",
    "tasks_per_joule": "tasks/J",
}
ENERGY_METRICS = frozenset({"energy_joules", "energy_per_token_j", "tasks_per_joule"})
# What the counter observed. ERA labels every energy metric with its scope and never
# turns a narrow scope into a claim about wall power.
ENERGY_SCOPES = {
    "gpu_counter_only": "GPU counter only. Not wall power.",
    "cpu_package": "CPU package counter. Not wall power.",
    "system_wall": "Wall power at the system.",
}
DEFAULT_P95_MIN_SAMPLES = 20
DEFAULT_P99_MIN_SAMPLES = 100
PERCENTILES = (50, 95, 99)


def percentile(sorted_values: list[float], p: int) -> float:
    """Nearest-rank percentile. Deterministic and needs no interpolation."""
    rank = max(1, math.ceil(p / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def variance_class(values: list[float]) -> str:
    """Same thresholds as the timing lane: under 5 percent is stable, under 15 is moderate."""
    if len(values) < 2:
        return "single_sample"
    mean = statistics.fmean(values)
    if mean == 0:
        return "stable"
    coefficient = statistics.stdev(values) / mean
    if coefficient < 0.05:
        return "stable"
    return "moderate_variance" if coefficient < 0.15 else "unstable"


def base_metric_name(name: str) -> str:
    for p in PERCENTILES:
        suffix = f"_p{p}"
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def validate_telemetry_policy(policy: Any) -> list[str]:
    if not isinstance(policy, dict):
        return ["evaluation.telemetry_policy must be an object."]
    errors: list[str] = []
    if not isinstance(policy.get("telemetry_results_path"), str) or not policy["telemetry_results_path"]:
        errors.append("evaluation.telemetry_policy needs telemetry_results_path.")
    percentile_metrics = policy.get("percentile_metrics", [])
    if not isinstance(percentile_metrics, list) or any(name not in KNOWN_METRICS for name in percentile_metrics):
        errors.append("evaluation.telemetry_policy.percentile_metrics must name known metrics.")
    if "energy_scope" in policy and policy["energy_scope"] not in ENERGY_SCOPES:
        errors.append(f"evaluation.telemetry_policy.energy_scope must be one of {sorted(ENERGY_SCOPES)}.")
    for key in ("p95_min_samples", "p99_min_samples"):
        value = policy.get(key, 1)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"evaluation.telemetry_policy.{key} must be a positive integer.")
    return errors


def read_telemetry(repo_path: Path, cwd_subpath: str, relative: str) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Return ``(payload, file_sha256, problems)``. The path must stay inside the target repo."""
    root = repo_path.resolve()
    target = ((root / cwd_subpath) / relative).resolve()
    if target != root and root not in target.parents:
        return None, None, [f"telemetry_results_path `{relative}` escapes the target repository."]
    if not target.is_file():
        return None, None, [f"Telemetry file `{relative}` does not exist."]
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, [f"Telemetry file `{relative}` is not valid JSON."]
    if not isinstance(payload, dict) or payload.get("schema_version") != TELEMETRY_SCHEMA:
        return None, None, [f"Telemetry file `{relative}` is not {TELEMETRY_SCHEMA}."]
    if not isinstance(payload.get("samples"), dict) or not isinstance(payload.get("measurement_scope"), str):
        return None, None, [f"Telemetry file `{relative}` needs samples and measurement_scope."]
    return payload, sha256_path(target), []


def _clean(values: Any) -> list[float] | None:
    if not isinstance(values, list) or not values:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values):
        return None
    return [float(v) for v in values]


def summarize_telemetry(
    payload: dict[str, Any],
    directions: dict[str, str],
    telemetry_policy: dict[str, Any],
) -> dict[str, Any]:
    """Turn raw samples into metric entries.

    Only metrics whose direction the manifest declares are used. A metric with bad
    samples is left out and named in ``problems``. A percentile whose sample count is
    too low is left out and named in ``notes``.
    """
    samples = payload["samples"]
    p95_min = int(telemetry_policy.get("p95_min_samples", DEFAULT_P95_MIN_SAMPLES))
    p99_min = int(telemetry_policy.get("p99_min_samples", DEFAULT_P99_MIN_SAMPLES))
    with_percentiles = set(telemetry_policy.get("percentile_metrics") or [])
    metrics: dict[str, dict[str, Any]] = {}
    per_metric_variance: dict[str, str] = {}
    per_metric_samples: dict[str, int] = {}
    uncertainty: dict[str, Any] = {}
    problems: list[str] = []
    notes: list[str] = []
    declared_scope = telemetry_policy.get("energy_scope")
    reported = payload.get("energy") if isinstance(payload.get("energy"), dict) else {}
    scope_problem = None
    if any(name in ENERGY_METRICS for name in directions):
        if declared_scope not in ENERGY_SCOPES:
            scope_problem = "Energy metrics need telemetry_policy.energy_scope."
        elif reported.get("scope") != declared_scope:
            scope_problem = (
                f"Energy scope mismatch: manifest declares `{declared_scope}`, "
                f"telemetry reports `{reported.get('scope')}`."
            )

    for name in sorted(KNOWN_METRICS):
        if name not in directions:
            continue
        if name in ENERGY_METRICS and scope_problem:
            problems.append(f"Energy metric `{name}` left out. {scope_problem}")
            continue
        if name not in samples:
            problems.append(f"Declared metric `{name}` has no samples in the telemetry file.")
            continue
        values = _clean(samples[name])
        if values is None:
            problems.append(f"Metric `{name}` has empty or invalid samples.")
            continue
        ordered = sorted(values)
        unit = KNOWN_METRICS[name]
        metrics[name] = {
            "value": statistics.median(ordered),
            "unit": unit,
            "direction": directions[name],
            "aggregation": "median",
            "sample_count": len(ordered),
            **({"scope": declared_scope} if name in ENERGY_METRICS else {}),
        }
        interval = bootstrap_median_ci(values)
        uncertainty[name] = interval or {
            "omitted": f"{len(ordered)} samples is below the minimum {MIN_SAMPLES_FOR_CI} for an interval."
        }
        per_metric_variance[name] = variance_class(values)
        per_metric_samples[name] = len(ordered)
        if name not in with_percentiles:
            continue
        for p, minimum in ((50, 1), (95, p95_min), (99, p99_min)):
            label = f"{name}_p{p}"
            if len(ordered) < minimum:
                notes.append(f"{label} omitted: {len(ordered)} samples is below the minimum {minimum}.")
                continue
            metrics[label] = {
                "value": percentile(ordered, p),
                "unit": unit,
                "direction": directions.get(label, directions[name]),
                "aggregation": f"p{p}",
                "sample_count": len(ordered),
                **({"scope": declared_scope} if name in ENERGY_METRICS else {}),
            }
            per_metric_variance[label] = per_metric_variance[name]
            per_metric_samples[label] = len(ordered)
    return {
        "metrics": metrics,
        "per_metric_variance": per_metric_variance,
        "per_metric_sample_count": per_metric_samples,
        "uncertainty": uncertainty,
        "problems": problems,
        "notes": notes,
    }
