"""Execution-isolation receipt for BDS-ERA-EVAL-v0.1 (WP11).

Operator ruling 2 (2026-09-30) names ``era_core/sandbox.py`` as the authorized
isolation provider. ERA records what the run actually had. It does not decide that
a run is safe. A workload with agentic, tool-rich, generated-code, external-repo, or
untrusted traits may make a claim only when its run was contained.

A contained run is not a full jail. It can still read other host paths. The
receipt says so in ``limitations``.
"""

from __future__ import annotations

from typing import Any

from era_core.artifact_paths import utc_now_text
from era_core.eval_contracts import _check_enum, _check_hash, _check_required, _check_schema, _seal

ISOLATION_SCHEMA = "IsolationReceipt.v1"
PROVIDER = "era_core.sandbox"
PROVIDER_AUTHORITY = "operator ruling 2, 2026-09-30"
STATUSES = frozenset({"satisfied", "unsatisfied", "not_required"})

# Traits that make a workload isolation-required (plan decision D5).
RISK_TRAITS = frozenset({"agentic", "mcp_tools", "generated_code", "external_repo", "untrusted"})
POSTURE_KEYS = ("sandbox", "sandbox_backend", "network", "target_filesystem")
# What a contained run must show. Anything else is not isolated.
CONTAINED = {"sandbox": "contained", "network": "isolated", "target_filesystem": "overlay_protected"}
LIMITATIONS = (
    "A contained run is not a full jail. The namespace can still read other host paths.",
    "ERA records the posture. It does not certify that the workload is safe.",
)


def validate_workload_traits(policy: dict[str, Any]) -> list[str]:
    traits = policy.get("workload_traits", [])
    if not isinstance(traits, list) or any(t not in RISK_TRAITS for t in traits):
        return [f"evaluation.workload_traits must list traits from {sorted(RISK_TRAITS)}."]
    return []


def isolation_requirement(policy: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return ``(required, reasons)``. Nothing in the manifest can turn a required run off."""
    reasons: list[str] = []
    if policy.get("subject_kind") == "agent":
        reasons.append("subject_kind is agent")
    reasons.extend(f"workload trait `{trait}`" for trait in sorted(set(policy.get("workload_traits") or [])))
    return bool(reasons), reasons


def evaluate_isolation(posture: dict[str, Any], required: bool) -> str:
    if not required:
        return "not_required"
    return "satisfied" if all(posture.get(key) == value for key, value in CONTAINED.items()) else "unsatisfied"


def build_isolation_receipt(
    *,
    fingerprint: dict[str, Any],
    posture: dict[str, Any],
    target_trust: str,
    read_only_invariant_scope: str,
    required: bool,
    required_reasons: list[str],
    created_at: str | None = None,
) -> dict[str, Any]:
    recorded = {key: posture.get(key) for key in POSTURE_KEYS}
    recorded["target_trust"] = target_trust
    recorded["read_only_invariant_scope"] = read_only_invariant_scope
    return _seal(
        {
            "schema_version": ISOLATION_SCHEMA,
            "isolation_receipt_id": f"isolation:{fingerprint['workload_id']}:{fingerprint['run_id']}",
            "run_id": fingerprint["run_id"],
            "workload_id": fingerprint["workload_id"],
            "config_fingerprint_id": fingerprint["fingerprint_id"],
            "config_fingerprint_sha256": fingerprint["sha256"],
            "provider": PROVIDER,
            "provider_authority": PROVIDER_AUTHORITY,
            "posture": recorded,
            "isolation_required": required,
            "required_reasons": required_reasons,
            "status": evaluate_isolation(recorded, required),
            "limitations": list(LIMITATIONS),
            "created_at": created_at or utc_now_text(),
        }
    )


def validate_isolation_receipt(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "IsolationReceipt"
    if not _check_schema(payload, ISOLATION_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "isolation_receipt_id", "run_id", "workload_id", "config_fingerprint_id", "config_fingerprint_sha256",
            "provider", "provider_authority", "posture", "isolation_required", "required_reasons", "status",
            "limitations", "created_at",
        ),
        label,
        errors,
    )
    _check_enum(payload, "status", STATUSES, label, errors)
    if not errors:
        if payload["provider"] != PROVIDER:
            errors.append(f"{label} provider `{payload['provider']}` is not the authorized provider.")
        if not isinstance(payload["posture"], dict) or not isinstance(payload["isolation_required"], bool):
            errors.append(f"{label} posture or isolation_required is malformed.")
        else:
            expected = evaluate_isolation(payload["posture"], payload["isolation_required"])
            if expected != payload["status"]:
                errors.append(f"{label} status `{payload['status']}` contradicts its posture (`{expected}`).")
            if payload["isolation_required"] and not payload["required_reasons"]:
                errors.append(f"{label} is required but names no reason.")
        if not payload["limitations"]:
            errors.append(f"{label} must state the limitations of a contained run.")
    _check_hash(payload, label, errors)
    return errors
