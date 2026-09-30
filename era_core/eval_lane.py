"""Quality-gated efficiency evidence for BDS-ERA-EVAL-v0.1 (WP03).

A workload opts in with an ``evaluation`` block (``EfficiencyWorkloadManifest.v2``
semantics). A workload without the block keeps the legacy v1 behavior. ERA reads
quality results from a file that already exists in the target tree. ERA does not
run a judge, call a model, or write to the target.

Manifest block::

    "evaluation": {
      "subject_kind": "repository_command",
      "subject_identity": {...},          # optional; command digest is derived
      "runtime_identity": {...},
      "evaluation_identity": {...},       # all nine EVALUATION_IDENTITY_FIELDS
      "execution_identity": {...},        # sandbox posture is added by ERA
      "quality_gate_policy": {
        "quality_floors": {"accuracy": {"min": 0.9}},
        "quality_results_path": "quality/results.json"
      },
      "metrics": {"median_ms": "lower_is_better"},
      "required_comparison_dimensions": [...],   # optional
      "non_binding_dimensions": [...]            # optional
    }

The results file is ``{"metric_results": {...}, "sample_count": N}``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_comparability import DEFAULT_REQUIRED_DIMENSIONS, is_known_dimension
from era_core.eval_contracts import (
    EVALUATION_IDENTITY_FIELDS,
    METRIC_DIRECTIONS,
    SUBJECT_KINDS,
    build_config_fingerprint,
    build_metric_vector,
    build_quality_gate_artifact,
    check_evidence_linkage,
    validate_config_fingerprint,
    validate_metric_vector,
    validate_quality_gate_artifact,
)
from era_core.hashing import sha256_json, sha256_path
from era_core.models import CommandResult

MANIFEST_V2_SCHEMA = "EfficiencyWorkloadManifest.v2"
POSTURE_KEYS = ("sandbox", "sandbox_backend", "network", "target_filesystem")


def eval_policy(workload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the workload's evaluation block, or None for a legacy workload."""
    policy = workload.get("evaluation")
    return policy if isinstance(policy, dict) else None


def validate_eval_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("subject_kind") not in SUBJECT_KINDS:
        errors.append(f"evaluation.subject_kind must be one of {sorted(SUBJECT_KINDS)}.")
    evaluation = policy.get("evaluation_identity")
    if not isinstance(evaluation, dict):
        errors.append("evaluation.evaluation_identity must be an object.")
    else:
        for field in EVALUATION_IDENTITY_FIELDS:
            if evaluation.get(field) in (None, ""):
                errors.append(f"evaluation.evaluation_identity is missing `{field}`.")
    for group in ("subject_identity", "runtime_identity", "execution_identity"):
        if group in policy and not isinstance(policy[group], dict):
            errors.append(f"evaluation.{group} must be an object.")
    gate_policy = policy.get("quality_gate_policy")
    if not isinstance(gate_policy, dict) or not gate_policy.get("quality_floors"):
        errors.append("evaluation.quality_gate_policy needs quality_floors.")
    elif not isinstance(gate_policy.get("quality_results_path"), str):
        errors.append("evaluation.quality_gate_policy needs quality_results_path.")
    metrics = policy.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        errors.append("evaluation.metrics must declare at least one metric direction.")
    else:
        for name, direction in metrics.items():
            if direction not in METRIC_DIRECTIONS:
                errors.append(f"evaluation.metrics.{name} has an unsupported direction.")
    for key in ("required_comparison_dimensions", "non_binding_dimensions"):
        for name in policy.get(key, []) or []:
            if not isinstance(name, str) or not is_known_dimension(name):
                errors.append(f"evaluation.{key} names an unrecognized dimension `{name}`.")
    return errors


def required_dimensions(policy: dict[str, Any]) -> tuple[str, ...]:
    declared = tuple(policy.get("required_comparison_dimensions") or ())
    return tuple(dict.fromkeys(DEFAULT_REQUIRED_DIMENSIONS + declared))


def _read_quality_results(
    repo_path: Path, cwd_subpath: str, relative: str
) -> tuple[dict[str, Any], int, list[str], str | None, list[str]]:
    """Return ``(metric_results, sample_count, raw_refs, sha256, problems)``."""
    root = repo_path.resolve()
    target = ((root / cwd_subpath) / relative).resolve()
    if target != root and root not in target.parents:
        return {}, 0, [], None, [f"quality_results_path `{relative}` escapes the target repository."]
    if not target.is_file():
        return {}, 0, [], None, [f"Quality results file `{relative}` does not exist."]
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, 0, [], None, [f"Quality results file `{relative}` is not valid JSON."]
    results = payload.get("metric_results") if isinstance(payload, dict) else None
    count = payload.get("sample_count") if isinstance(payload, dict) else None
    if not isinstance(results, dict) or not isinstance(count, int) or isinstance(count, bool):
        return {}, 0, [], None, [f"Quality results file `{relative}` needs metric_results and sample_count."]
    digest = sha256_path(target)
    return results, count, [f"quality_results:{relative}:sha256:{digest}"], digest, []


def build_workload_eval_evidence(
    *,
    run_id: str,
    repo_id: str,
    repo_path: Path,
    commit_sha: str,
    workload: dict[str, Any],
    command_result: CommandResult | None,
    execution_posture: dict[str, Any],
) -> dict[str, Any]:
    """Build the fingerprint, quality gate, and metric vector for one v2 workload.

    Never raises for bad evidence. The result carries ``quality_status`` and
    ``problems``. A misdeclared workload has status ``invalid``.
    """
    policy = eval_policy(workload) or {}
    workload_id = workload.get("workload_id")
    problems = validate_eval_policy(policy)
    evidence: dict[str, Any] = {
        "workload_id": workload_id,
        "fingerprint": None,
        "quality_gate": None,
        "metric_vector": None,
        "quality_status": "invalid",
        "problems": problems,
    }
    if problems:
        return evidence

    command = workload.get("command") or []
    subject_identity = {
        "executable": command[0] if command else None,
        "command_digest": sha256_json(command),
        **(policy.get("subject_identity") or {}),
    }
    execution_identity = {
        **(policy.get("execution_identity") or {}),
        **{key: execution_posture.get(key) for key in POSTURE_KEYS if key in execution_posture},
    }
    fingerprint = build_config_fingerprint(
        run_id=run_id,
        repo_id=repo_id,
        workload_id=workload_id,
        subject_kind=policy["subject_kind"],
        source_commit_sha=commit_sha,
        subject_identity=subject_identity,
        runtime_identity=policy.get("runtime_identity") or {},
        evaluation_identity=policy["evaluation_identity"],
        execution_identity=execution_identity,
    )
    evidence["fingerprint"] = fingerprint

    gate_policy = policy["quality_gate_policy"]
    results, count, refs, _, read_problems = _read_quality_results(
        repo_path, workload.get("cwd_subpath", "."), gate_policy["quality_results_path"]
    )
    gate = build_quality_gate_artifact(
        fingerprint=fingerprint,
        metric_results=results,
        quality_floors=gate_policy["quality_floors"],
        sample_count=count,
        raw_evidence_refs=refs,
    )
    if read_problems:
        gate["failure_reasons"] = read_problems + [
            reason for reason in gate["failure_reasons"] if reason not in read_problems
        ]
        gate["sha256"] = sha256_json({k: v for k, v in gate.items() if k != "sha256"})
    evidence["quality_gate"] = gate
    evidence["quality_status"] = gate["gate_status"]

    summary = ((command_result.lane_metadata or {}).get("timing_summary") if command_result else None) or {}
    if command_result is not None and command_result.status == "passed" and "median_ms" in summary:
        directions = policy["metrics"]
        if "median_ms" in directions:
            evidence["metric_vector"] = build_metric_vector(
                fingerprint=fingerprint,
                metrics={
                    "median_ms": {
                        "value": summary["median_ms"],
                        "unit": "ms",
                        "direction": directions["median_ms"],
                    }
                },
                sample_count=len((command_result.lane_metadata or {}).get("iteration_durations_ms") or []),
                variance_or_uncertainty={
                    "variance_classification": (command_result.lane_metadata or {}).get("variance_classification"),
                    "stdev_ms": summary.get("stdev_ms"),
                },
                measurement_scope="wall_clock_internal_timer",
                raw_evidence_refs=[f"{command_result.command_id}:stdout", f"{command_result.command_id}:stderr"],
            )

    integrity = (
        validate_config_fingerprint(fingerprint)
        + validate_quality_gate_artifact(gate)
        + (validate_metric_vector(evidence["metric_vector"]) if evidence["metric_vector"] else [])
        + check_evidence_linkage(fingerprint, gate, evidence["metric_vector"])
    )
    if integrity:
        evidence["problems"] = integrity
        evidence["quality_status"] = "invalid"
    return evidence


def build_eval_evidence(
    *,
    run_id: str,
    repo_id: str,
    repo_path: Path,
    commit_sha: str,
    manifest: dict[str, Any],
    command_results: list[CommandResult],
    execution_posture: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return ``workload_id -> evidence`` for every v2 workload in the manifest."""
    by_workload = {
        (item.lane_metadata or {}).get("workload_id"): item for item in command_results
    }
    evidence: dict[str, dict[str, Any]] = {}
    for workload in manifest.get("workloads", []):
        if eval_policy(workload) is None or not workload.get("workload_id"):
            continue
        evidence[workload["workload_id"]] = build_workload_eval_evidence(
            run_id=run_id,
            repo_id=repo_id,
            repo_path=repo_path,
            commit_sha=commit_sha,
            workload=workload,
            command_result=by_workload.get(workload["workload_id"]),
            execution_posture=execution_posture,
        )
    return evidence


QUALITY_CLAIM_BY_STATUS = {
    "failed": "quality_blocked",
    "unproven": "quality_unproven",
    "invalid": "evidence_blocked",
}


def apply_quality_gate(baseline_artifact: dict[str, Any], eval_evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Block improvement and regression claims for a workload whose quality is not proven.

    The timing result stays visible as ``timing_comparison_status``. A quality
    failure is the controlling status. It is never reduced to a regression.
    Legacy workloads (no entry in ``eval_evidence``) are left as they are.
    """
    for comparison in baseline_artifact.get("comparisons", []):
        evidence = eval_evidence.get(comparison["workload_id"])
        if evidence is None:
            continue
        comparison["evaluation"] = True
        comparison["quality_status"] = evidence["quality_status"]
        comparison["fingerprint_id"] = (evidence["fingerprint"] or {}).get("fingerprint_id")
        comparison["timing_comparison_status"] = comparison["comparison_status"]
        blocked = QUALITY_CLAIM_BY_STATUS.get(evidence["quality_status"])
        if blocked and comparison["comparison_status"] != "workload_failed_or_unproven":
            comparison["comparison_status"] = blocked
            comparison["blocked_reasons"] = (
                evidence["quality_gate"]["failure_reasons"]
                if evidence["quality_gate"] and evidence["quality_status"] != "invalid"
                else evidence["problems"]
            )
    baseline_artifact["sha256"] = sha256_json({k: v for k, v in baseline_artifact.items() if k != "sha256"})
    return baseline_artifact
