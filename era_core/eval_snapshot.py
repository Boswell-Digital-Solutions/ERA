"""Baseline snapshot for BDS-ERA-EVAL-v0.1 (operator decision 4: keep the baseline chain).

A comparison names a baseline run. Without a snapshot, the baseline run folder must
stay on disk, and archiving an old run breaks every newer run that used it. The
snapshot copies the baseline evidence into the newer run, so a consumer can check
the claim without the old folder.
"""

from __future__ import annotations

from typing import Any

from era_core.artifact_paths import utc_now_text
from era_core.eval_contracts import (
    _check_hash,
    _check_required,
    _check_schema,
    _seal,
    check_evidence_linkage,
    validate_config_fingerprint,
    validate_metric_vector,
    validate_quality_gate_artifact,
)

SNAPSHOT_SCHEMA = "BaselineSnapshot.v1"
_PARTS = ("fingerprint", "quality_gate", "metric_vector")


def build_baseline_snapshot(
    *,
    candidate_fingerprint: dict[str, Any],
    baseline: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Copy the chosen baseline's evidence. ``baseline`` is a loaded prior (run_id + three artifacts)."""
    fingerprint, gate, vector = baseline["fingerprint"], baseline["quality_gate"], baseline["metric_vector"]
    return _seal(
        {
            "schema_version": SNAPSHOT_SCHEMA,
            "baseline_snapshot_id": f"baseline_snapshot:{candidate_fingerprint['workload_id']}:{candidate_fingerprint['run_id']}",
            "run_id": candidate_fingerprint["run_id"],
            "workload_id": candidate_fingerprint["workload_id"],
            "candidate_fingerprint_id": candidate_fingerprint["fingerprint_id"],
            "baseline_run_id": baseline["run_id"],
            "baseline_fingerprint_id": fingerprint["fingerprint_id"],
            "baseline_config_digest": fingerprint["config_digest"],
            "baseline_quality_status": gate["gate_status"],
            "fingerprint": fingerprint,
            "quality_gate": gate,
            "metric_vector": vector,
            "part_hashes": {name: baseline[name]["sha256"] for name in _PARTS},
            "created_at": created_at or utc_now_text(),
        }
    )


def validate_baseline_snapshot(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "BaselineSnapshot"
    if not _check_schema(payload, SNAPSHOT_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "baseline_snapshot_id", "run_id", "workload_id", "candidate_fingerprint_id", "baseline_run_id",
            "baseline_fingerprint_id", "baseline_config_digest", "baseline_quality_status", "part_hashes", "created_at",
            *_PARTS,
        ),
        label,
        errors,
    )
    if errors:
        return errors
    errors.extend(f"{label} fingerprint: {e}" for e in validate_config_fingerprint(payload["fingerprint"]))
    errors.extend(f"{label} quality gate: {e}" for e in validate_quality_gate_artifact(payload["quality_gate"]))
    errors.extend(f"{label} metric vector: {e}" for e in validate_metric_vector(payload["metric_vector"]))
    if not errors:
        errors.extend(f"{label}: {e}" for e in check_evidence_linkage(payload["fingerprint"], payload["quality_gate"], payload["metric_vector"]))
        for name in _PARTS:
            if payload["part_hashes"].get(name) != payload[name].get("sha256"):
                errors.append(f"{label} part hash for {name} does not match the copied artifact.")
        if payload["baseline_fingerprint_id"] != payload["fingerprint"]["fingerprint_id"]:
            errors.append(f"{label} baseline_fingerprint_id does not match the copied fingerprint.")
        if payload["baseline_config_digest"] != payload["fingerprint"]["config_digest"]:
            errors.append(f"{label} baseline_config_digest does not match the copied fingerprint.")
        if payload["baseline_run_id"] != payload["fingerprint"]["run_id"]:
            errors.append(f"{label} baseline_run_id does not match the copied fingerprint.")
        if payload["baseline_quality_status"] != payload["quality_gate"]["gate_status"]:
            errors.append(f"{label} baseline_quality_status does not match the copied quality gate.")
    _check_hash(payload, label, errors)
    return errors
