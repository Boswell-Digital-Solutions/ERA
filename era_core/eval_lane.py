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
import re
from pathlib import Path
from typing import Any

from era_core.eval_claims import (
    COMPARISON_STATUS_BY_CLAIM,
    build_comparison_artifact,
    decide_claim,
    load_prior_evidence,
    select_eligible_baseline,
)
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
from era_core.eval_telemetry import (
    read_telemetry,
    summarize_telemetry,
    validate_telemetry_policy,
)
from era_core.eval_agent import (
    AGENT_SUBJECT_FIELDS,
    SUCCESS_METRIC,
    read_agent_evidence,
    summarize_agent,
    validate_agent_policy,
    validate_agent_subject,
)
from era_core.eval_judge import (
    build_judge_audit,
    read_judge_evidence,
    thresholds_from,
    validate_judge_audit,
    validate_judge_policy,
)
from era_core.eval_stats import bootstrap_median_ci
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
    if isinstance(gate_policy, dict) and "judge_policy" in gate_policy:
        judge_errors = validate_judge_policy(gate_policy["judge_policy"])
        errors.extend(judge_errors)
        if not judge_errors:
            for name in gate_policy["judge_policy"]["judge_metrics"]:
                if name not in (gate_policy.get("quality_floors") or {}):
                    errors.append(f"judge metric `{name}` has no quality floor.")
    metrics = policy.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        errors.append("evaluation.metrics must declare at least one metric direction.")
    else:
        for name, direction in metrics.items():
            if direction not in METRIC_DIRECTIONS:
                errors.append(f"evaluation.metrics.{name} has an unsupported direction.")
    primary = policy.get("primary_metric", "median_ms")
    if isinstance(metrics, dict) and metrics:
        if primary not in metrics:
            errors.append(f"evaluation.primary_metric `{primary}` is not a declared metric.")
        elif metrics[primary] not in {"lower_is_better", "higher_is_better"}:
            errors.append("evaluation.primary_metric needs lower_is_better or higher_is_better.")
    if policy.get("subject_kind") == "agent":
        errors.extend(validate_agent_subject(policy.get("subject_identity")))
    if "agent_policy" in policy:
        errors.extend(validate_agent_policy(policy["agent_policy"], policy.get("subject_kind"), policy.get("subject_identity")))
    if "sample_policy" in policy:
        errors.extend(validate_sample_policy(policy["sample_policy"]))
    if "telemetry_policy" in policy:
        errors.extend(validate_telemetry_policy(policy["telemetry_policy"]))
    for key in ("required_comparison_dimensions", "non_binding_dimensions"):
        for name in policy.get(key, []) or []:
            if not isinstance(name, str) or not is_known_dimension(name):
                errors.append(f"evaluation.{key} names an unrecognized dimension `{name}`.")
    return errors


TELEMETRY_SENSITIVE_DIMENSIONS = (
    "execution.hardware_fingerprint",
    "execution.concurrency",
    "execution.batch_size",
)


def validate_sample_policy(sample_policy: Any) -> list[str]:
    if not isinstance(sample_policy, dict):
        return ["evaluation.sample_policy must be an object."]
    errors: list[str] = []
    warmup = sample_policy.get("warmup_iterations", 0)
    if isinstance(warmup, bool) or not isinstance(warmup, int) or not 0 <= warmup <= 20:
        errors.append("evaluation.sample_policy.warmup_iterations must be an integer from 0 to 20.")
    minimum = sample_policy.get("min_samples", 0)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        errors.append("evaluation.sample_policy.min_samples must be a non-negative integer.")
    if not isinstance(sample_policy.get("require_ci_separation", False), bool):
        errors.append("evaluation.sample_policy.require_ci_separation must be true or false.")
    return errors


def required_dimensions(policy: dict[str, Any]) -> tuple[str, ...]:
    """Default dimensions, the manifest's own, and, for telemetry, the hardware-bound ones.

    Hardware, concurrency, and batch size change latency and throughput. A manifest
    can waive one only through ``non_binding_dimensions``.
    """
    declared = tuple(policy.get("required_comparison_dimensions") or ())
    telemetry = TELEMETRY_SENSITIVE_DIMENSIONS if "telemetry_policy" in policy else ()
    scope_declared = (policy.get("telemetry_policy") or {}).get("energy_scope") or (
        policy.get("agent_policy") or {}
    ).get("energy_scope")
    energy = ("execution.energy_scope",) if scope_declared else ()
    agent = (
        tuple(f"subject.{field}" for field in AGENT_SUBJECT_FIELDS) + TELEMETRY_SENSITIVE_DIMENSIONS
        if policy.get("subject_kind") == "agent"
        else ()
    )
    return tuple(dict.fromkeys(DEFAULT_REQUIRED_DIMENSIONS + telemetry + agent + energy + declared))


def sample_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("sample_policy")
    return value if isinstance(value, dict) else {}


def primary_metric(policy: dict[str, Any]) -> str:
    return policy.get("primary_metric", "median_ms")


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
        "judge_audit": None,
        "problems": problems,
        "telemetry_problems": [],
        "telemetry_notes": [],
        "agent_problems": [],
    }
    if problems:
        return evidence

    command = workload.get("command") or []
    subject_identity = {
        "executable": command[0] if command else None,
        "command_digest": sha256_json(command),
        **(policy.get("subject_identity") or {}),
    }
    energy_scope = (policy.get("telemetry_policy") or {}).get("energy_scope") or (
        policy.get("agent_policy") or {}
    ).get("energy_scope")
    execution_identity = {
        **(policy.get("execution_identity") or {}),
        **({"energy_scope": energy_scope} if energy_scope else {}),
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
    agent_summary = None
    agent_ref = None
    agent_policy = policy.get("agent_policy")
    if agent_policy:
        agent_payload, agent_digest, agent_read_problems = read_agent_evidence(
            repo_path, workload.get("cwd_subpath", "."), agent_policy["agent_evidence_path"]
        )
        evidence["agent_problems"] = list(agent_read_problems)
        if agent_payload is not None:
            agent_summary = summarize_agent(agent_payload, policy["metrics"], agent_policy)
            agent_summary["measurement_scope"] = agent_payload["measurement_scope"]
            evidence["agent_problems"] += agent_summary["problems"]
            if agent_summary["success_rate"] is not None:
                # The success rate comes from the hashed agent evidence, so the harness cannot restate it.
                results[SUCCESS_METRIC] = agent_summary["success_rate"]
                count = count or agent_summary["task_count"]
            agent_ref = f"agent_evidence:{agent_policy['agent_evidence_path']}:sha256:{agent_digest}"
            refs.append(agent_ref)
    judge_policy = gate_policy.get("judge_policy")
    if judge_policy:
        judge_evidence, judge_digest, judge_problems = read_judge_evidence(
            repo_path, workload.get("cwd_subpath", "."), judge_policy["judge_evidence_path"]
        )
        audit = build_judge_audit(
            fingerprint=fingerprint,
            evidence=judge_evidence,
            read_problems=judge_problems,
            thresholds=thresholds_from(judge_policy),
            judge_metrics=list(judge_policy["judge_metrics"]),
            raw_evidence_refs=[f"judge_evidence:{judge_policy['judge_evidence_path']}:sha256:{judge_digest}"]
            if judge_digest
            else [],
        )
        evidence["judge_audit"] = audit
        if audit["audit_status"] != "passed":
            # A judge metric counts only after a passed audit. Without one the floor has no result.
            for name in judge_policy["judge_metrics"]:
                if name in results:
                    del results[name]
                read_problems.append(f"Judge metric `{name}` not admitted: the judge audit is `{audit['audit_status']}`.")
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
    directions = policy["metrics"]
    if command_result is not None and command_result.status == "passed":
        lane_metadata = command_result.lane_metadata or {}
        metrics: dict[str, dict[str, Any]] = {}
        per_metric_variance: dict[str, str] = {}
        per_metric_samples: dict[str, int] = {}
        refs = [f"{command_result.command_id}:stdout", f"{command_result.command_id}:stderr"]
        scopes = ["wall_clock_internal_timer"]
        uncertainty: dict[str, Any] = {}
        if "median_ms" in summary and "median_ms" in directions:
            durations = [float(v) for v in lane_metadata.get("iteration_durations_ms") or []]
            metrics["median_ms"] = {"value": summary["median_ms"], "unit": "ms", "direction": directions["median_ms"]}
            per_metric_variance["median_ms"] = lane_metadata.get("variance_classification")
            per_metric_samples["median_ms"] = len(durations)
            uncertainty["median_ms"] = bootstrap_median_ci(durations) or {
                "omitted": f"{len(durations)} samples is below the minimum for an interval."
            }
        telemetry_policy = policy.get("telemetry_policy")
        if telemetry_policy:
            payload, digest, read_problems = read_telemetry(
                repo_path, workload.get("cwd_subpath", "."), telemetry_policy["telemetry_results_path"]
            )
            evidence["telemetry_problems"] = list(read_problems)
            if payload is not None:
                summarized = summarize_telemetry(payload, directions, telemetry_policy)
                metrics.update(summarized["metrics"])
                per_metric_variance.update(summarized["per_metric_variance"])
                per_metric_samples.update(summarized["per_metric_sample_count"])
                uncertainty.update(summarized["uncertainty"])
                evidence["telemetry_problems"] += summarized["problems"]
                evidence["telemetry_notes"] = summarized["notes"]
                refs.append(f"telemetry_results:{telemetry_policy['telemetry_results_path']}:sha256:{digest}")
                scopes.append(payload["measurement_scope"])
        if agent_summary is not None:
            metrics.update(agent_summary["metrics"])
            per_metric_variance.update(agent_summary["per_metric_variance"])
            per_metric_samples.update(agent_summary["per_metric_sample_count"])
            uncertainty.update(agent_summary["uncertainty"])
            refs.append(agent_ref)
            scopes.append(agent_summary["measurement_scope"])
        if metrics:
            evidence["metric_vector"] = build_metric_vector(
                fingerprint=fingerprint,
                metrics=metrics,
                sample_count=min(per_metric_samples.values()) if per_metric_samples else 0,
                variance_or_uncertainty={
                    "variance_classification": lane_metadata.get("variance_classification"),
                    "stdev_ms": summary.get("stdev_ms"),
                    "per_metric": per_metric_variance,
                    "per_metric_sample_count": per_metric_samples,
                    "uncertainty": uncertainty,
                    "warmup_iterations": lane_metadata.get("warmup_iterations", 0),
                },
                measurement_scope="+".join(dict.fromkeys(scopes)),
                raw_evidence_refs=refs,
            )

    integrity = (
        validate_config_fingerprint(fingerprint)
        + validate_quality_gate_artifact(gate)
        + (validate_judge_audit(evidence["judge_audit"]) if evidence["judge_audit"] else [])
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


def workload_dirname(workload_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", workload_id.lower()).strip("_")


def resolve_comparisons(
    *,
    run_id: str,
    artifacts_root: Path,
    manifest: dict[str, Any],
    eval_evidence: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Select a comparable baseline and decide the claim for every v2 workload."""
    workloads = {item.get("workload_id"): item for item in manifest.get("workloads", [])}
    comparisons: dict[str, dict[str, Any]] = {}
    for workload_id, candidate in eval_evidence.items():
        workload = workloads[workload_id]
        policy = eval_policy(workload) or {}
        selection: dict[str, Any] = {"baseline": None, "comparison": None, "rejected": [], "considered": 0}
        if candidate["fingerprint"] is not None:
            priors = load_prior_evidence(artifacts_root, run_id, workload_id, workload_dirname(workload_id))
            selection = select_eligible_baseline(
                candidate["fingerprint"],
                priors,
                required_dimensions(policy),
                tuple(policy.get("non_binding_dimensions") or ()),
            )
        decision = decide_claim(
            candidate=candidate,
            selection=selection,
            regression_threshold_pct=float(workload.get("regression_threshold_pct", 10.0)),
            improvement_threshold_pct=float(workload.get("improvement_threshold_pct", 10.0)),
            primary_metric=primary_metric(policy),
            min_samples=int(sample_policy(policy).get("min_samples", 0)),
            require_ci_separation=bool(sample_policy(policy).get("require_ci_separation", False)),
        )
        comparisons[workload_id] = build_comparison_artifact(
            run_id=run_id,
            workload_id=workload_id,
            candidate=candidate,
            selection=selection,
            decision=decision,
        )
    return comparisons


def apply_quality_gate(
    baseline_artifact: dict[str, Any],
    eval_evidence: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replace the timing-only status of each v2 workload with its gated claim.

    The timing result stays visible as ``timing_comparison_status``. A quality
    failure is the controlling status. It is never reduced to a regression.
    Legacy workloads (no entry in ``eval_evidence``) are left as they are.
    Without ``comparisons`` only the quality gate applies (WP03 behavior).
    """
    for comparison in baseline_artifact.get("comparisons", []):
        evidence = eval_evidence.get(comparison["workload_id"])
        if evidence is None:
            continue
        artifact = (comparisons or {}).get(comparison["workload_id"])
        comparison["evaluation"] = True
        comparison["quality_status"] = evidence["quality_status"]
        comparison["fingerprint_id"] = (evidence["fingerprint"] or {}).get("fingerprint_id")
        comparison["timing_comparison_status"] = comparison["comparison_status"]
        if artifact is not None:
            claim = artifact["claim_status"]
            comparison["claim_status"] = claim
            comparison["comparability_status"] = artifact["comparability_status"]
            comparison["baseline_run_id"] = artifact["baseline_run_id"]
            comparison["blocked_reasons"] = artifact["blocked_reasons"]
            primary = artifact.get("primary_metric", "median_ms")
            delta = artifact["metric_deltas"].get(primary)
            comparison["primary_metric"] = primary
            comparison["baseline_median_ms"] = delta["baseline"] if delta and primary == "median_ms" else None
            comparison["delta_ms"] = delta["delta"] if delta else None
            comparison["delta_pct"] = delta["delta_pct"] if delta else None
            if claim == "permitted":
                comparison["comparison_status"] = artifact["efficiency_status"]
            elif comparison["comparison_status"] != "workload_failed_or_unproven":
                comparison["comparison_status"] = COMPARISON_STATUS_BY_CLAIM[claim]
            continue
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
