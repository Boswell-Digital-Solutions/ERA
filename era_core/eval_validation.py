"""Fail-closed validation of quality-gated evaluation evidence (WP05).

Every check appends an error string. An empty list means the evidence chain for
the run is intact. The checks cover: file presence, file hash against the bundle
reference and the hash chain, embedded hash and schema of each artifact, run and
fingerprint linkage, agreement between the comparison, its inputs and the
baseline artifact, and the baseline reference itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_claims import COMPARISON_STATUS_BY_CLAIM, PRIMARY_METRIC
from era_core.eval_comparability import compare_fingerprints
from era_core.eval_contracts import (
    check_evidence_linkage,
    validate_config_fingerprint,
    validate_metric_vector,
    validate_quality_efficiency_comparison,
    validate_quality_gate_artifact,
)
from era_core.eval_isolation import POSTURE_KEYS, isolation_requirement, validate_isolation_receipt
from era_core.eval_judge import validate_judge_audit
from era_core.eval_lane import eval_policy, required_dimensions, workload_dirname
from era_core.eval_review import EVAL_KINDS
from era_core.eval_snapshot import validate_baseline_snapshot
from era_core.hashing import sha256_json, sha256_path

_VALIDATORS = {
    "fingerprint": validate_config_fingerprint,
    "quality_gate": validate_quality_gate_artifact,
    "metric_vector": validate_metric_vector,
    "judge_audit": validate_judge_audit,
    "isolation_receipt": validate_isolation_receipt,
    "baseline_snapshot": validate_baseline_snapshot,
    "comparison": validate_quality_efficiency_comparison,
}


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def validate_eval_evidence(
    *,
    run_dir: Path,
    run_artifact: dict[str, Any],
    efficiency_bundle: dict[str, Any],
    baseline_artifact: dict[str, Any],
    chain: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    manifest = efficiency_bundle.get("workload_manifest") or {}
    v2_workloads = {
        item["workload_id"]: item
        for item in manifest.get("workloads", [])
        if isinstance(item, dict) and item.get("workload_id") and eval_policy(item) is not None
    }
    refs = efficiency_bundle.get("evaluation_evidence_refs") or {}

    for workload_id in v2_workloads:
        if workload_id not in refs:
            errors.append(f"Evaluation workload {workload_id} has no evaluation evidence refs.")
    for workload_id in refs:
        if workload_id not in v2_workloads:
            errors.append(f"Evaluation evidence refs name unknown workload {workload_id}.")

    chain_entries = {
        (item.get("workload_id"), item.get("kind")): item for item in chain.get("evaluation_artifacts", []) or []
    }
    expected_keys: set[tuple[str, str]] = set()
    run_id = run_artifact["run_id"]

    for workload_id, entry in sorted(refs.items()):
        label = f"Evaluation evidence for {workload_id}"
        loaded: dict[str, dict[str, Any]] = {}
        for kind in EVAL_KINDS:
            ref = entry.get(kind)
            if not ref:
                continue
            expected_keys.add((workload_id, kind))
            path = run_dir / ref["path"]
            if not path.is_file():
                errors.append(f"{label}: {kind} file is missing ({ref['path']}).")
                continue
            if sha256_path(path) == ref["sha256"]:
                pass
            else:
                # The file hash covers formatting. The reference hash is the embedded hash.
                payload = _load(path)
                if payload is None or payload.get("sha256") != ref["sha256"]:
                    errors.append(f"{label}: {kind} hash does not match its reference.")
            payload = _load(path)
            if payload is None:
                errors.append(f"{label}: {kind} is not valid JSON.")
                continue
            if payload.get("sha256") != ref["sha256"]:
                errors.append(f"{label}: {kind} embedded hash does not match its reference.")
            loaded[kind] = payload
            errors.extend(f"{label}: {item}" for item in _VALIDATORS[kind](payload))
            if payload.get("run_id") not in (None, run_id) or (
                kind == "comparison" and payload.get("candidate_run_id") != run_id
            ):
                errors.append(f"{label}: {kind} run_id does not match run.json.")
            if payload.get("workload_id") != workload_id:
                errors.append(f"{label}: {kind} names another workload.")
            chain_entry = chain_entries.get((workload_id, kind))
            if chain_entry is None:
                errors.append(f"Evidence hash chain missing {kind} for {workload_id}.")
            elif chain_entry.get("sha256") != ref["sha256"] or chain_entry.get("path") != ref["path"]:
                errors.append(f"Evidence hash chain has stale {kind} reference for {workload_id}.")

        judge_policy = ((eval_policy(v2_workloads.get(workload_id, {})) or {}).get("quality_gate_policy") or {}).get(
            "judge_policy"
        )
        errors.extend(_check_completeness(label, entry, loaded, judge_required=bool(judge_policy)))
        errors.extend(f"{label}: {item}" for item in _check_linkage(loaded))
        errors.extend(f"{label}: {item}" for item in _check_judge(loaded, judge_policy))
        errors.extend(
            f"{label}: {item}"
            for item in _check_isolation(loaded, eval_policy(v2_workloads.get(workload_id, {})) or {})
        )
        comparison = loaded.get("comparison")
        if comparison is not None:
            errors.extend(
                f"{label}: {item}"
                for item in _check_comparison(
                    run_dir=run_dir,
                    workload_id=workload_id,
                    workload=v2_workloads.get(workload_id, {}),
                    loaded=loaded,
                    baseline_artifact=baseline_artifact,
                )
            )

    for key in chain_entries:
        if key not in expected_keys:
            errors.append(f"Evidence hash chain references missing evaluation artifact {key[1]} for {key[0]}.")
    return errors


def _check_isolation(loaded: dict[str, dict[str, Any]], policy: dict[str, Any]) -> list[str]:
    """The receipt must match the fingerprint, the manifest, and the comparison."""
    receipt, fingerprint, comparison = loaded.get("isolation_receipt"), loaded.get("fingerprint"), loaded.get("comparison")
    if receipt is None or fingerprint is None:
        return []
    errors: list[str] = []
    if receipt.get("config_fingerprint_id") != fingerprint.get("fingerprint_id"):
        errors.append("isolation receipt references a different config fingerprint id.")
    if receipt.get("config_fingerprint_sha256") != fingerprint.get("sha256"):
        errors.append("isolation receipt references a different config fingerprint digest.")
    identity = fingerprint.get("execution_identity") or {}
    for key in POSTURE_KEYS:
        if (receipt.get("posture") or {}).get(key) != identity.get(key):
            errors.append(f"isolation receipt posture `{key}` differs from the fingerprint execution identity.")
    required, _ = isolation_requirement(policy)
    if receipt.get("isolation_required") != required:
        errors.append("isolation receipt requirement differs from the manifest.")
    if comparison is not None and comparison.get("isolation_status") != receipt.get("status"):
        errors.append("comparison isolation_status does not match the isolation receipt.")
    return errors


def _check_judge(loaded: dict[str, dict[str, Any]], judge_policy: dict[str, Any] | None) -> list[str]:
    """A judge metric may sit in the quality gate only after a passed audit."""
    audit, gate = loaded.get("judge_audit"), loaded.get("quality_gate")
    if audit is None or gate is None:
        return []
    errors: list[str] = []
    fingerprint = loaded.get("fingerprint")
    if fingerprint is not None:
        if audit.get("config_fingerprint_id") != fingerprint.get("fingerprint_id"):
            errors.append("judge audit references a different config fingerprint id.")
        if audit.get("config_fingerprint_sha256") != fingerprint.get("sha256"):
            errors.append("judge audit references a different config fingerprint digest.")
    if audit.get("audit_status") != "passed":
        admitted = [m for m in audit.get("judge_metrics", []) if m in (gate.get("metric_results") or {})]
        if admitted:
            errors.append(f"judge metrics {admitted} are in the quality gate without a passed audit.")
        if gate.get("gate_status") == "passed":
            errors.append("quality gate passed although the judge audit did not pass.")
    if judge_policy and sorted(audit.get("judge_metrics", [])) != sorted(judge_policy.get("judge_metrics", [])):
        errors.append("judge audit metrics differ from the manifest judge_policy.")
    return errors


def _check_completeness(
    label: str, entry: dict[str, Any], loaded: dict[str, dict[str, Any]], judge_required: bool = False
) -> list[str]:
    errors: list[str] = []
    if "comparison" not in loaded:
        errors.append(f"{label}: comparison artifact is missing.")
        return errors
    claim = loaded["comparison"].get("claim_status")
    if entry.get("quality_status") != "invalid":
        for kind in ("fingerprint", "quality_gate"):
            if kind not in loaded:
                errors.append(f"{label}: {kind} artifact is missing.")
    if entry.get("quality_status") != "invalid" and "isolation_receipt" not in loaded:
        errors.append(f"{label}: isolation_receipt artifact is missing.")
    if judge_required and entry.get("quality_status") != "invalid" and "judge_audit" not in loaded:
        errors.append(f"{label}: judge_audit artifact is missing.")
    if loaded["comparison"].get("baseline_run_id") and "baseline_snapshot" not in loaded:
        errors.append(f"{label}: baseline_snapshot artifact is missing.")
    if claim in {"permitted", "no_claim_unstable"} and "metric_vector" not in loaded:
        errors.append(f"{label}: metric_vector artifact is missing for claim `{claim}`.")
    if claim not in {"evidence_blocked"} and entry.get("quality_status") == "invalid":
        errors.append(f"{label}: invalid evidence must give an evidence_blocked claim.")
    return errors


def _check_linkage(loaded: dict[str, dict[str, Any]]) -> list[str]:
    fingerprint = loaded.get("fingerprint")
    if fingerprint is None:
        return []
    errors = check_evidence_linkage(fingerprint, loaded.get("quality_gate"), loaded.get("metric_vector"))
    comparison = loaded.get("comparison")
    if comparison is not None and comparison.get("candidate_fingerprint_id") != fingerprint.get("fingerprint_id"):
        errors.append("comparison candidate_fingerprint_id does not match the fingerprint.")
    gate = loaded.get("quality_gate")
    if comparison is not None and gate is not None and comparison.get("quality_status") != gate.get("gate_status"):
        errors.append("comparison quality_status does not match the quality gate.")
    return errors


def _check_comparison(
    *,
    run_dir: Path,
    workload_id: str,
    workload: dict[str, Any],
    loaded: dict[str, dict[str, Any]],
    baseline_artifact: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    comparison = loaded["comparison"]
    claim = comparison["claim_status"]

    entry = next((c for c in baseline_artifact.get("comparisons", []) if c.get("workload_id") == workload_id), None)
    if entry is None:
        errors.append("baseline artifact has no entry for this workload.")
    elif entry.get("claim_status") != claim:
        errors.append("baseline artifact claim_status does not match the comparison.")
    elif entry.get("comparison_status") != "workload_failed_or_unproven":
        expected = comparison["efficiency_status"] if claim == "permitted" else COMPARISON_STATUS_BY_CLAIM.get(claim)
        if entry.get("comparison_status") != expected:
            errors.append(
                f"baseline artifact status `{entry.get('comparison_status')}` does not match the comparison (`{expected}`)."
            )

    baseline_run = comparison.get("baseline_run_id")
    if claim in {"permitted", "no_claim_unstable"} and not baseline_run:
        errors.append("claim needs a baseline run but none is recorded.")
    if baseline_run:
        errors.extend(_check_baseline_reference(run_dir, workload_id, workload, loaded, comparison))
    if claim == "permitted":
        primary = comparison.get("primary_metric", PRIMARY_METRIC)
        declared = (eval_policy(workload) or {}).get("primary_metric", PRIMARY_METRIC)
        if primary != declared:
            errors.append(f"comparison primary_metric `{primary}` differs from the manifest (`{declared}`).")
        delta = (comparison.get("metric_deltas") or {}).get(primary)
        vector = loaded.get("metric_vector")
        if delta is None or vector is None:
            errors.append("permitted claim has no metric delta.")
        elif delta.get("candidate") != vector["metrics"].get(primary, {}).get("value"):
            errors.append("comparison candidate value does not match the metric vector.")
    return errors


def _check_baseline_reference(
    run_dir: Path,
    workload_id: str,
    workload: dict[str, Any],
    loaded: dict[str, dict[str, Any]],
    comparison: dict[str, Any],
) -> list[str]:
    """The recorded baseline must be proven by the run's own snapshot.

    The baseline run folder is not needed. When it still exists it must agree with
    the snapshot, so a forger cannot edit the folder and keep a passing snapshot.
    """
    baseline_run = comparison["baseline_run_id"]
    snapshot = loaded.get("baseline_snapshot")
    if snapshot is None:
        return [f"baseline run {baseline_run} has no baseline snapshot in this run."]
    errors: list[str] = []
    if snapshot["baseline_run_id"] != baseline_run:
        errors.append(f"baseline snapshot is for run {snapshot['baseline_run_id']}, not {baseline_run}.")
    if snapshot["baseline_fingerprint_id"] != comparison.get("baseline_fingerprint_id"):
        errors.append(f"baseline run {baseline_run} has a different fingerprint than the comparison records.")
    if snapshot["baseline_quality_status"] != "passed":
        errors.append(f"baseline run {baseline_run} did not pass its quality gate.")
    candidate = loaded.get("fingerprint")
    if candidate is not None and snapshot.get("candidate_fingerprint_id") != candidate.get("fingerprint_id"):
        errors.append("baseline snapshot belongs to a different candidate fingerprint.")
    if candidate is not None:
        policy = eval_policy(workload) or {}
        match = compare_fingerprints(
            candidate,
            snapshot["fingerprint"],
            required_dimensions(policy),
            tuple(policy.get("non_binding_dimensions") or ()),
        )
        if match["comparability_status"] != "comparable":
            errors.append(f"baseline run {baseline_run} is not comparable: " + " ".join(match["blocked_reasons"]))
    delta = (comparison.get("metric_deltas") or {}).get(comparison.get("primary_metric", PRIMARY_METRIC))
    baseline_metric = (snapshot["metric_vector"].get("metrics") or {}).get(comparison.get("primary_metric", PRIMARY_METRIC))
    if delta is not None and baseline_metric is not None and delta.get("baseline") != baseline_metric.get("value"):
        errors.append("comparison baseline value does not match the baseline snapshot.")

    directory = run_dir.parent / baseline_run / "evidence" / "efficiency" / "eval" / workload_dirname(workload_id)
    for name in ("fingerprint", "quality_gate", "metric_vector"):
        original = _load(directory / f"{name}.json")
        # Compare the recomputed hash. An edit that keeps the old embedded hash still differs.
        actual = sha256_json({k: v for k, v in (original or {}).items() if k != "sha256"}) if original else None
        if original is not None and actual != snapshot["part_hashes"].get(name):
            errors.append(f"baseline run folder {baseline_run} differs from the baseline snapshot ({name}).")
    return errors
