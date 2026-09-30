"""Evaluation export for downstream systems (BDS-ERA-EVAL-v0.1 WP12, ERA side).

ERA writes one ``ERAEvaluationExport.v1`` into each run that has opted-in
workloads. It is the producer interface for a later DataForge Local persistence
slice and a Forge_Command review surface. ERA does not write to either system.

The export is a summary of files that already exist in the run folder. Validation
rebuilds it from those files and rejects any difference, so it cannot say more
than the evidence says. It is ERA evidence. It is not canonical truth until a
downstream owner reconciles and reviews it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_review import EVAL_KINDS
from era_core.hashing import sha256_json

EXPORT_SCHEMA = "ERAEvaluationExport.v1"
EXPORT_FILENAME = "evaluation_export.json"
AUTHORITY_STATEMENT = (
    "ERA evidence only. Not canonical truth until reconciled and reviewed downstream. "
    "ERA holds no approval, promotion, routing, or mutation authority."
)
CONSUMER_CONTRACT_STATUS = "local_to_era"  # not promoted to forge_contract_core (AUTHORITY_GAP-01)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _baseline_block(snapshot: dict[str, Any] | None, ref: dict[str, Any] | None) -> dict[str, Any] | None:
    """The baseline evidence, so a consumer keeps the chain when the baseline run folder is archived."""
    if snapshot is None:
        return None
    vector = snapshot.get("metric_vector") or {}
    return {
        "run_id": snapshot["baseline_run_id"],
        "fingerprint_id": snapshot["baseline_fingerprint_id"],
        "config_digest": snapshot["baseline_config_digest"],
        "quality_status": snapshot["baseline_quality_status"],
        "metrics": {
            name: {key: metric[key] for key in ("value", "unit", "direction", "aggregation", "scope") if key in metric}
            for name, metric in sorted((vector.get("metrics") or {}).items())
        },
        "part_hashes": snapshot["part_hashes"],
        "snapshot_digest": snapshot["sha256"],
        "snapshot_path": (ref or {}).get("path"),
    }


def build_evaluation_export(run_dir: Path) -> dict[str, Any] | None:
    """Build the export from the run folder. Return None when no workload opted in."""
    run = _load(run_dir / "run.json")
    bundle = _load(run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json")
    if run is None or bundle is None:
        return None
    refs = bundle.get("evaluation_evidence_refs") or {}
    if not refs:
        return None
    findings = _load(run_dir / "findings.json") or {}
    lane_score = next(
        (s for s in findings.get("era_scores", []) if s.get("scope") == "lane" and s.get("lane") == "efficiency"), {}
    )
    workloads: list[dict[str, Any]] = []
    for workload_id in sorted(refs):
        entry = refs[workload_id]
        loaded = {kind: _load(run_dir / entry[kind]["path"]) for kind in EVAL_KINDS if entry.get(kind)}
        comparison = loaded.get("comparison") or {}
        fingerprint = loaded.get("fingerprint") or {}
        vector = loaded.get("metric_vector") or {}
        audit = loaded.get("judge_audit")
        snapshot = loaded.get("baseline_snapshot")
        workloads.append(
            {
                "workload_id": workload_id,
                "claim_status": comparison.get("claim_status"),
                "quality_status": comparison.get("quality_status"),
                "comparability_status": comparison.get("comparability_status"),
                "efficiency_status": comparison.get("efficiency_status"),
                "isolation_status": comparison.get("isolation_status"),
                "primary_metric": comparison.get("primary_metric"),
                "judge_audit_status": audit.get("audit_status") if audit else None,
                "fingerprint_id": fingerprint.get("fingerprint_id"),
                "config_digest": fingerprint.get("config_digest"),
                "subject_kind": fingerprint.get("subject_kind"),
                "baseline_run_id": comparison.get("baseline_run_id"),
                "baseline_fingerprint_id": comparison.get("baseline_fingerprint_id"),
                "blocked_reasons": comparison.get("blocked_reasons", []),
                "baseline": _baseline_block(snapshot, entry.get("baseline_snapshot")),
                "baseline_rejection_reasons": sorted(
                    {item.get("reason") for item in comparison.get("baseline_rejections", []) if item.get("reason")}
                ),
                "metrics": {
                    name: {
                        key: metric[key]
                        for key in ("value", "unit", "direction", "aggregation", "scope")
                        if key in metric
                    }
                    for name, metric in sorted((vector.get("metrics") or {}).items())
                },
                "measurement_scope": vector.get("measurement_scope"),
                "metric_deltas": comparison.get("metric_deltas", {}),
                "artifacts": {
                    kind: {"path": entry[kind]["path"], "sha256": entry[kind]["sha256"]}
                    for kind in EVAL_KINDS
                    if entry.get(kind)
                },
            }
        )
    payload = {
        "schema_version": EXPORT_SCHEMA,
        "run_id": run["run_id"],
        "repo_id": run["repo_id"],
        "commit_sha": run["commit_sha"],
        "run_status": run["status"],
        "efficiency_lane_classification": lane_score.get("classification"),
        "execution_posture": run.get("execution_posture"),
        "workloads": workloads,
        "authority": AUTHORITY_STATEMENT,
        "consumer_contract_status": CONSUMER_CONTRACT_STATUS,
        "created_at": run["completed_at"],
    }
    payload["sha256"] = sha256_json(payload)
    return payload


def validate_evaluation_export(run_dir: Path, chain: dict[str, Any]) -> list[str]:
    """Rebuild the export and compare. Fail closed on any difference or missing piece."""
    expected = build_evaluation_export(run_dir)
    path = run_dir / EXPORT_FILENAME
    entry = chain.get("evaluation_export")
    if expected is None:
        if path.exists() or entry:
            return ["An evaluation export exists but the run has no opted-in workload."]
        return []
    errors: list[str] = []
    stored = _load(path)
    if stored is None:
        return [f"{EXPORT_FILENAME} is missing or not valid JSON."]
    if stored.get("schema_version") != EXPORT_SCHEMA:
        errors.append(f"{EXPORT_FILENAME} has an invalid schema_version.")
    if stored.get("authority") != AUTHORITY_STATEMENT:
        errors.append(f"{EXPORT_FILENAME} authority statement was changed.")
    if stored != expected:
        differing = sorted(key for key in set(stored) | set(expected) if stored.get(key) != expected.get(key))
        errors.append(f"{EXPORT_FILENAME} differs from the run evidence in: {', '.join(differing)}.")
    if not entry:
        errors.append("Evidence hash chain is missing the evaluation export.")
    elif entry.get("sha256") != stored.get("sha256") or entry.get("path") != EXPORT_FILENAME:
        errors.append("Evidence hash chain has a stale evaluation export reference.")
    return errors
