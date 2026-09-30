"""Projection of ERA's evaluation summary to the admitted ``era_evaluation_export`` v1 contract.

The contract is owned by ``forge_contract_core`` (RFC-ERA-EVAL-01, accepted 2026-09-30).
ERA is the producer. This module has no dependency on that repository. It implements
the three rules a producer must apply, and ERA's tests check it against the contract's
own vectors and validator:

- a measured non-count quantity is a canonical decimal string (``canonical_decimal``)
- ``workloads[]`` and set-like arrays are in canonical order
- ``payload_digest`` is the self-digest under ``forge.rfc8785-jcs-sha256.v1``
  (integer-only JCS, domain ``forge:era-evaluation-export:v1``, digest field excluded)

The projection drops run-time identity (the attesting user) and local paths. It keeps
statuses, hashes, and metric summaries. ERA evidence only: no approval, promotion,
routing, mutation, deployment, or execution authority.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

FAMILY = "era_evaluation_export"
SCHEMA_VERSION = "era.evaluation_export.v1"
DOMAIN = b"forge:era-evaluation-export:v1\x00"
AUTHORITY = (
    "ERA evidence only. Not canonical truth until reconciled and reviewed downstream. "
    "ERA holds no approval, promotion, routing, or mutation authority."
)
NAMESPACE = uuid.UUID("2b0c8d53-6a52-5d0e-8a63-4c4f6f0e7a10")  # fixed, so an artifact id is stable for a run
MAX_REASON_LENGTH = 1024
MAX_REASONS = 64
MAX_WORKLOAD_ID = 128

POSTURE_KEYS = ("sandbox", "sandbox_backend", "network", "target_filesystem", "target_trust")
METRIC_KEYS = ("value", "unit", "direction", "aggregation", "scope")
INTERVAL_KEYS = ("method", "confidence", "resamples", "ci_low", "ci_high", "sample_count")
_LITERAL = re.compile(r"([+-]?)([0-9]*)(?:\.([0-9]*))?(?:[eE]([+-]?[0-9]+))?")
_MAX_EXPONENT = 1000
MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ProjectionError(ValueError):
    """The summary cannot be projected to the admitted contract."""


def canonical_decimal(value: Any) -> str:
    """The one canonical decimal string of a finite number. NaN, infinity, and bool raise."""
    if isinstance(value, bool):
        raise ProjectionError("a bool is not a number")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = repr(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ProjectionError(f"unsupported type {type(value).__name__}")
    match = _LITERAL.fullmatch(text)
    if match is None:
        raise ProjectionError(f"not a finite decimal literal: {text!r}")
    sign, int_part, frac_part, exponent_text = match.groups()
    frac_part = frac_part or ""
    if not int_part and not frac_part:
        raise ProjectionError(f"no digits in {text!r}")
    exponent = int(exponent_text) if exponent_text else 0
    if abs(exponent) > _MAX_EXPONENT:
        raise ProjectionError(f"exponent out of range in {text!r}")
    digits = int_part + frac_part
    point = len(int_part) + exponent
    stripped = digits.lstrip("0")
    point -= len(digits) - len(stripped)
    digits = stripped.rstrip("0")
    if not digits:
        return "0"
    if point <= 0:
        body = "0." + "0" * (-point) + digits
    elif point >= len(digits):
        body = digits + "0" * (point - len(digits))
    else:
        body = digits[:point] + "." + digits[point:]
    return ("-" if sign == "-" else "") + body


# -- JCS (integer-only subset) and the self-digest -------------------------------------------


def _jcs(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise ProjectionError(f"integer {value} is outside the interoperable JCS range")
        return str(value)
    if isinstance(value, float):
        raise ProjectionError("a JSON float is forbidden: use a decimal string or an integer count")
    if isinstance(value, str):
        return _jcs_string(value)
    if isinstance(value, list):
        return "[" + ",".join(_jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(f"{_jcs_string(key)}:{_jcs(value[key])}" for key in keys) + "}"
    raise ProjectionError(f"unsupported value type {type(value).__name__}")


def _jcs_string(text: str) -> str:
    short = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r"}
    out = ['"']
    for character in text:
        code = ord(character)
        if 0xD800 <= code <= 0xDFFF:
            raise ProjectionError("lone surrogate in a string")
        if character == '"':
            out.append('\\"')
        elif character == "\\":
            out.append("\\\\")
        elif code in short:
            out.append(short[code])
        elif code <= 0x1F:
            out.append(f"\\u{code:04x}")
        else:
            out.append(character)
    out.append('"')
    return "".join(out)


def payload_digest(payload: dict[str, Any]) -> str:
    """``sha256:<hex>`` over the domain-separated JCS bytes of the payload without ``payload_digest``."""
    projection = {key: value for key, value in payload.items() if key != "payload_digest"}
    return "sha256:" + hashlib.sha256(DOMAIN + _jcs(projection).encode("utf-8")).hexdigest()


# -- Projection ------------------------------------------------------------------------------


def _metric(entry: dict[str, Any]) -> dict[str, Any]:
    out = {key: entry[key] for key in METRIC_KEYS if key in entry}
    out["value"] = canonical_decimal(entry["value"])
    out.setdefault("aggregation", "median")  # median_ms is a median of iteration durations
    return out


def _interval(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    out = {key: entry[key] for key in INTERVAL_KEYS if key in entry}
    for key in ("confidence", "ci_low", "ci_high"):
        out[key] = canonical_decimal(out[key])
    return out


def _delta(entry: dict[str, Any]) -> dict[str, Any]:
    out = {
        "candidate": canonical_decimal(entry["candidate"]),
        "baseline": canonical_decimal(entry["baseline"]),
        "delta": canonical_decimal(entry["delta"]),
        "delta_pct": canonical_decimal(entry["delta_pct"]),
        "direction": entry["direction"],
        "outcome": entry["outcome"],
        "candidate_stability": entry.get("candidate_stability"),
        "baseline_stability": entry.get("baseline_stability"),
        "candidate_interval": _interval(entry.get("candidate_interval")),
        "baseline_interval": _interval(entry.get("baseline_interval")),
    }
    for key in ("scope", "baseline_scope"):
        if entry.get(key) is not None:
            out[key] = entry[key]
    return out


def _reasons(reasons: list[str]) -> list[str]:
    """Bound the narrative list. A long reason is cut; extra reasons are counted, not dropped silently."""
    cut = [text if len(text) <= MAX_REASON_LENGTH else text[: MAX_REASON_LENGTH - 3] + "..." for text in reasons]
    if len(cut) > MAX_REASONS:
        omitted = len(cut) - (MAX_REASONS - 1)
        cut = cut[: MAX_REASONS - 1] + [f"{omitted} more reasons were omitted from this export."]
    return cut


def _baseline(block: dict[str, Any] | None) -> dict[str, Any] | None:
    if block is None:
        return None
    return {
        "run_id": block["run_id"],
        "fingerprint_id": block["fingerprint_id"],
        "config_digest": block["config_digest"],
        "quality_status": block["quality_status"],
        "metrics": {name: _metric(m) for name, m in sorted(block["metrics"].items())},
        "part_hashes": dict(block["part_hashes"]),
        "snapshot_digest": block["snapshot_digest"],
    }


def _workload(w: dict[str, Any]) -> dict[str, Any]:
    if not 1 <= len(w["workload_id"]) <= MAX_WORKLOAD_ID:
        raise ProjectionError(f"workload_id must be 1 to {MAX_WORKLOAD_ID} characters")
    return {
        "workload_id": w["workload_id"],
        "subject_kind": w["subject_kind"],
        "fingerprint_id": w["fingerprint_id"],
        "config_digest": w["config_digest"],
        "claim_status": w["claim_status"],
        "quality_status": w["quality_status"],
        "comparability_status": w["comparability_status"],
        "efficiency_status": w["efficiency_status"],
        "isolation_status": w["isolation_status"],
        "judge_audit_status": w["judge_audit_status"],
        "primary_metric": w["primary_metric"],
        "measurement_scope": w["measurement_scope"],
        "metrics": {name: _metric(m) for name, m in sorted(w["metrics"].items())},
        "metric_deltas": {name: _delta(d) for name, d in sorted(w["metric_deltas"].items())},
        "blocked_reasons": _reasons(list(w["blocked_reasons"])),
        "baseline_rejection_reasons": sorted(set(w["baseline_rejection_reasons"])),
        "baseline_run_id": w["baseline_run_id"],
        "baseline_fingerprint_id": w["baseline_fingerprint_id"],
        "baseline": _baseline(w["baseline"]),
        "artifacts": {kind: {"path": ref["path"], "sha256": ref["sha256"]} for kind, ref in sorted(w["artifacts"].items())},
    }


def to_contract_payload(summary: dict[str, Any]) -> dict[str, Any]:
    """Project ERA's run summary to the admitted payload, with ``payload_digest`` set."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": summary["run_id"],
        "repository_id": summary["repo_id"],
        "commit_sha": summary["commit_sha"],
        "run_status": summary["run_status"],
        "efficiency_lane_classification": summary["efficiency_lane_classification"],
        "execution_posture": {key: summary["execution_posture"][key] for key in POSTURE_KEYS},
        "authority": AUTHORITY,
        "workloads": sorted((_workload(w) for w in summary["workloads"]), key=lambda w: w["workload_id"]),
        "created_at": summary["created_at"],
    }
    ids = [w["workload_id"] for w in payload["workloads"]]
    if len(set(ids)) != len(ids):
        raise ProjectionError("duplicate workload_id")
    payload["payload_digest"] = payload_digest(payload)
    return payload


def build_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap the payload in the shared envelope. Deterministic for one run.

    The ``signature`` field is an unsigned digest reference, not a cryptographic
    signature: ERA holds no signing key. The prefix ``unsigned:`` says so.
    """
    artifact_id = str(uuid.uuid5(NAMESPACE, f"{payload['run_id']}|{FAMILY}"))
    return {
        "artifact_id": artifact_id,
        "artifact_family": FAMILY,
        "artifact_version": 1,
        "produced_by_system": "ERA",
        "produced_by_component": "era.evaluation-export",
        "source_scope": "local",
        "lineage_root_id": artifact_id,
        "parent_artifact_id": None,
        "trace_id": f"trace-era-evaluation-export-{payload['run_id']}"[:128],
        "idempotency_key": hashlib.sha256(f"{FAMILY}|{artifact_id}|1|{artifact_id}".encode()).hexdigest(),
        "created_at": payload["created_at"],
        "recorded_at": payload["created_at"],
        "sensitivity_class": "internal",
        "visibility_class": "operator",
        "promotion_class": "local_only",
        "validation_status": "valid",
        "signer_identity": "ERA/era.evaluation-export",
        "signature": "unsigned:" + payload["payload_digest"],
        "payload": payload,
    }
