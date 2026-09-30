"""Claim gate for BDS-ERA-EVAL-v0.1 (WP04).

The order of checks is fixed. A claim forms only after quality and comparability
pass. Every doubt gives a status that blocks the claim.

1. Broken or missing evidence         -> evidence_blocked
2. Quality failed                     -> quality_blocked
3. Quality unproven                   -> quality_unproven
4. No prior run at all                -> no_baseline
5. Prior runs, none eligible          -> incomparable (or evidence_blocked when only unknown)
6. Unstable candidate or baseline     -> no_claim_unstable
7. Metric delta against thresholds    -> permitted (improvement, regression, within_range)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_comparability import compare_fingerprints, select_baseline
from era_core.eval_stats import intervals_overlap
from era_core.eval_contracts import (
    build_quality_efficiency_comparison,
    check_evidence_linkage,
    validate_config_fingerprint,
    validate_metric_vector,
    validate_quality_gate_artifact,
)

PRIMARY_METRIC = "median_ms"
UNSTABLE_CLASSES = {"unstable", "single_sample"}


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def load_prior_evidence(artifacts_root: Path, run_id: str, workload_id: str, dirname: str) -> list[dict[str, Any]]:
    """Return evaluation evidence of prior runs for one workload.

    ``dirname`` is the sanitized workload directory name. A run with no evidence
    for the workload is skipped. A run with a broken file is kept, so that the
    selector can reject it with a reason.
    """
    priors: list[dict[str, Any]] = []
    if not artifacts_root.is_dir():
        return priors
    for run_dir in sorted(artifacts_root.iterdir()):
        directory = run_dir / "evidence" / "efficiency" / "eval" / dirname
        if run_dir.name == run_id or not directory.is_dir():
            continue
        priors.append(
            {
                "run_id": run_dir.name,
                "fingerprint": _load(directory / "fingerprint.json"),
                "quality_gate": _load(directory / "quality_gate.json"),
                "metric_vector": _load(directory / "metric_vector.json"),
            }
        )
    return priors


def _prior_problems(prior: dict[str, Any]) -> list[str]:
    """Return reasons a prior run's evidence is unusable (before quality or comparability)."""
    fingerprint, gate, vector = prior["fingerprint"], prior["quality_gate"], prior["metric_vector"]
    if fingerprint is None or gate is None or vector is None:
        return ["Prior evaluation evidence is incomplete."]
    problems = (
        validate_config_fingerprint(fingerprint)
        + validate_quality_gate_artifact(gate)
        + validate_metric_vector(vector)
        + check_evidence_linkage(fingerprint, gate, vector)
    )
    return ["Prior evaluation evidence does not validate: " + "; ".join(problems)] if problems else []


REJECTION_EVIDENCE_INVALID = "evidence_invalid"
REJECTION_INCOMPARABLE = "fingerprint_incomparable"
REJECTION_QUALITY_FAILED = "quality_failed"
REJECTION_QUALITY_UNPROVEN = "quality_unproven"


def select_eligible_baseline(
    candidate_fingerprint: dict[str, Any],
    priors: list[dict[str, Any]],
    required_dimensions: tuple[str, ...],
    non_binding_dimensions: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Pick the latest prior run that is a qualified baseline.

    A prior run is eligible only when (1) its evidence validates, (2) its
    fingerprint matches the required dimensions, and (3) its quality gate
    passed. Every rejected run stays in ``rejected`` with a reason, one of
    ``evidence_invalid``, ``fingerprint_incomparable``, ``quality_failed``, or
    ``quality_unproven``. Checks run in that order.
    """
    by_run = {prior["run_id"]: prior for prior in priors}
    rejected: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for prior in priors:
        problems = _prior_problems(prior)
        if problems:
            rejected.append(
                {
                    "run_id": prior["run_id"],
                    "reason": REJECTION_EVIDENCE_INVALID,
                    "comparability_status": "unknown",
                    "blocked_reasons": problems,
                }
            )
            continue
        match = compare_fingerprints(
            candidate_fingerprint, prior["fingerprint"], required_dimensions, non_binding_dimensions
        )
        if match["comparability_status"] != "comparable":
            rejected.append(
                {
                    "run_id": prior["run_id"],
                    "reason": REJECTION_INCOMPARABLE,
                    "comparability_status": match["comparability_status"],
                    "blocked_reasons": match["blocked_reasons"],
                }
            )
            continue
        gate_status = prior["quality_gate"]["gate_status"]
        if gate_status != "passed":
            rejected.append(
                {
                    "run_id": prior["run_id"],
                    "reason": REJECTION_QUALITY_FAILED if gate_status == "failed" else REJECTION_QUALITY_UNPROVEN,
                    "comparability_status": "comparable",
                    "blocked_reasons": [f"Prior quality gate is `{gate_status}`, so it is not a fair baseline."],
                }
            )
            continue
        eligible.append(prior["fingerprint"])
    selection = select_baseline(candidate_fingerprint, eligible, required_dimensions, non_binding_dimensions)
    return {
        "baseline": by_run.get(selection["baseline_run_id"]) if selection["baseline_found"] else None,
        "comparison": selection["comparison"],
        "rejected": rejected,
        "considered": len(priors),
    }


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    delta = candidate["value"] - baseline["value"]
    delta_pct = 0.0 if baseline["value"] == 0 else round(delta / baseline["value"] * 100.0, 3)
    return {
        "candidate": candidate["value"],
        "baseline": baseline["value"],
        "delta": delta,
        "delta_pct": delta_pct,
        "direction": candidate["direction"],
    }


def decide_claim(
    *,
    candidate: dict[str, Any],
    selection: dict[str, Any],
    regression_threshold_pct: float,
    improvement_threshold_pct: float,
    primary_metric: str = PRIMARY_METRIC,
    min_samples: int = 0,
    require_ci_separation: bool = False,
) -> dict[str, Any]:
    """Return the status fields of a ``QualityEfficiencyComparison.v1``.

    The claim rests on ``primary_metric`` only. Every other metric that both vectors
    carry gets its own delta and outcome. ERA never combines metrics into one score.
    """
    fingerprint, gate, vector = candidate["fingerprint"], candidate["quality_gate"], candidate["metric_vector"]
    quality_status = candidate["quality_status"]
    baseline = selection["baseline"]
    result: dict[str, Any] = {
        "quality_status": quality_status,
        "comparability_status": "unknown",
        "efficiency_status": "not_evaluated",
        "claim_status": "evidence_blocked",
        "comparison_dimensions": (selection["comparison"] or {}).get("comparison_dimensions", {}),
        "metric_deltas": {},
        "blocked_reasons": [],
        "primary_metric": primary_metric,
    }

    def block(claim: str, reasons: list[str]) -> dict[str, Any]:
        result["claim_status"] = claim
        result["blocked_reasons"] = reasons
        return result

    linkage = check_evidence_linkage(fingerprint, gate, vector) if fingerprint and gate else []
    if quality_status == "invalid" or linkage or fingerprint is None or gate is None:
        return block("evidence_blocked", candidate["problems"] + linkage or ["Evaluation evidence is invalid."])
    if quality_status == "failed":
        return block("quality_blocked", gate["failure_reasons"])
    if quality_status == "unproven":
        return block("quality_unproven", gate["failure_reasons"])
    if vector is None:
        return block("evidence_blocked", ["No metric vector exists for the candidate."])

    if baseline is None:
        rejected = selection["rejected"]
        reasons = [reason for item in rejected for reason in item["blocked_reasons"]]
        reason_set = {item["reason"] for item in rejected}
        if not selection["considered"]:
            return block("no_baseline", ["No prior run has evaluation evidence for this workload."])
        # Comparable priors exist but none passed quality: nothing eligible to compare against.
        if reason_set & {REJECTION_QUALITY_FAILED, REJECTION_QUALITY_UNPROVEN}:
            return block("no_baseline", ["No prior run is a qualified baseline."] + reasons)
        if any(item["comparability_status"] == "incomparable" for item in rejected):
            result["comparability_status"] = "incomparable"
            return block("incomparable", reasons)
        return block("evidence_blocked", reasons or ["No prior run is a usable baseline."])

    result["comparability_status"] = "comparable"
    baseline_vector = baseline["metric_vector"]
    candidate_metric = vector["metrics"].get(primary_metric)
    baseline_metric = baseline_vector["metrics"].get(primary_metric)
    if candidate_metric is None or baseline_metric is None:
        reasons = [f"Metric `{primary_metric}` is missing from a metric vector."] + candidate.get("telemetry_problems", []) + candidate.get("agent_problems", [])
        return block("evidence_blocked", reasons)
    direction = candidate_metric["direction"]
    if direction != baseline_metric["direction"]:
        return block("evidence_blocked", ["Candidate and baseline declare different metric directions."])
    if direction not in {"lower_is_better", "higher_is_better"}:
        return block("evidence_blocked", [f"Direction `{direction}` cannot support a claim."])

    result["metric_deltas"] = _all_deltas(
        vector, baseline_vector, regression_threshold_pct, improvement_threshold_pct
    )
    thin = [
        label
        for label, source in (("candidate", vector), ("baseline", baseline_vector))
        if min_samples and _sample_count(source, primary_metric) < min_samples
    ]
    if thin:
        result["efficiency_status"] = "unstable"
        return block(
            "no_claim_unstable",
            [f"The {' and '.join(thin)} `{primary_metric}` has fewer than the required {min_samples} samples."],
        )
    unstable = [
        label
        for label, source in (("candidate", vector), ("baseline", baseline_vector))
        if _stability(source, primary_metric) in UNSTABLE_CLASSES
    ]
    if unstable:
        result["efficiency_status"] = "unstable"
        return block("no_claim_unstable", [f"The {' and '.join(unstable)} `{primary_metric}` is too unstable for a claim."])

    outcome = result["metric_deltas"][primary_metric]["outcome"]
    if require_ci_separation and outcome in {"better", "worse"}:
        overlap = intervals_overlap(_interval(vector, primary_metric), _interval(baseline_vector, primary_metric))
        if overlap is None:
            result["efficiency_status"] = "unstable"
            return block("no_claim_unstable", [f"No confidence interval exists for `{primary_metric}`. Too few samples."])
        if overlap:
            result["efficiency_status"] = "unstable"
            return block(
                "no_claim_unstable",
                [f"The 95 percent intervals of `{primary_metric}` overlap, so the difference is not established."],
            )
    result["efficiency_status"] = {"better": "improvement", "worse": "regression", "within_range": "within_range"}[outcome]
    result["claim_status"] = "permitted"
    return result


def _stability(vector: dict[str, Any], metric: str) -> str | None:
    uncertainty = vector["variance_or_uncertainty"]
    return (uncertainty.get("per_metric") or {}).get(metric) or uncertainty.get("variance_classification")


def _sample_count(vector: dict[str, Any], metric: str) -> int:
    counts = vector["variance_or_uncertainty"].get("per_metric_sample_count") or {}
    return int(counts.get(metric, vector.get("sample_count", 0)))


def _interval(vector: dict[str, Any], metric: str) -> dict[str, Any] | None:
    entry = (vector["variance_or_uncertainty"].get("uncertainty") or {}).get(metric)
    return entry if isinstance(entry, dict) and "ci_low" in entry else None


def _all_deltas(
    vector: dict[str, Any],
    baseline_vector: dict[str, Any],
    regression_threshold_pct: float,
    improvement_threshold_pct: float,
) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    for name, candidate_metric in sorted(vector["metrics"].items()):
        baseline_metric = baseline_vector["metrics"].get(name)
        if baseline_metric is None:
            continue
        delta = _metric_delta(candidate_metric, baseline_metric)
        delta["candidate_stability"] = _stability(vector, name)
        delta["baseline_stability"] = _stability(baseline_vector, name)
        delta["candidate_interval"] = _interval(vector, name)
        delta["baseline_interval"] = _interval(baseline_vector, name)
        if candidate_metric.get("scope") or baseline_metric.get("scope"):
            delta["scope"] = candidate_metric.get("scope")
            delta["baseline_scope"] = baseline_metric.get("scope")
        direction = candidate_metric["direction"]
        if direction != baseline_metric["direction"]:
            delta["outcome"] = "direction_mismatch"
        elif direction not in {"lower_is_better", "higher_is_better"}:
            delta["outcome"] = "not_assessed"
        else:
            worse = delta["delta_pct"] if direction == "lower_is_better" else -delta["delta_pct"]
            if worse >= regression_threshold_pct:
                delta["outcome"] = "worse"
            elif worse <= -improvement_threshold_pct:
                delta["outcome"] = "better"
            else:
                delta["outcome"] = "within_range"
        deltas[name] = delta
    return deltas


COMPARISON_STATUS_BY_CLAIM = {
    "quality_blocked": "quality_blocked",
    "quality_unproven": "quality_unproven",
    "incomparable": "incomparable",
    "evidence_blocked": "evidence_blocked",
    "no_claim_unstable": "unstable",
    "no_baseline": "no_baseline",
}


def build_comparison_artifact(
    *,
    run_id: str,
    workload_id: str,
    candidate: dict[str, Any],
    selection: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    fingerprint = candidate["fingerprint"] or {}
    baseline = selection["baseline"]
    return build_quality_efficiency_comparison(
        run_id=run_id,
        workload_id=workload_id,
        candidate_fingerprint_id=fingerprint.get("fingerprint_id", "missing"),
        baseline_fingerprint_id=baseline["fingerprint"]["fingerprint_id"] if baseline else None,
        candidate_run_id=run_id,
        baseline_run_id=baseline["run_id"] if baseline else None,
        quality_status=decision["quality_status"],
        comparability_status=decision["comparability_status"],
        efficiency_status=decision["efficiency_status"],
        claim_status=decision["claim_status"],
        comparison_dimensions=decision["comparison_dimensions"],
        metric_deltas=decision["metric_deltas"],
        blocked_reasons=decision["blocked_reasons"],
        baseline_rejections=[
            {key: item[key] for key in ("run_id", "reason", "comparability_status", "blocked_reasons")}
            for item in selection["rejected"]
        ],
        primary_metric=decision.get("primary_metric", PRIMARY_METRIC),
    )
