"""Local contracts for BDS-ERA-EVAL-v0.1 (ERA-EVAL-01, WP01).

These contracts are local to ERA. They are not promoted to forge_contract_core.
Every builder seals its payload with a ``sha256`` over the canonical JSON of the
payload without the ``sha256`` key, the same convention as ``era_core.contracts``.
Every validator returns a list of error strings. An empty list means valid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from era_core.artifact_paths import utc_now_text
from era_core.eval_telemetry import ENERGY_METRICS, ENERGY_SCOPES, base_metric_name
from era_core.hashing import sha256_json

FINGERPRINT_SCHEMA = "EvaluationConfigFingerprint.v1"
QUALITY_GATE_SCHEMA = "QualityGateArtifact.v1"
METRIC_VECTOR_SCHEMA = "MetricVector.v1"
COMPARISON_SCHEMA = "QualityEfficiencyComparison.v1"

SUBJECT_KINDS = frozenset({"repository_command", "local_model", "provider_model", "agent"})
GATE_STATUSES = frozenset({"passed", "failed", "unproven", "invalid"})
COMPARABILITY_STATUSES = frozenset({"comparable", "incomparable", "unknown"})
EFFICIENCY_STATUSES = frozenset({"improvement", "regression", "within_range", "unstable", "not_evaluated"})
CLAIM_STATUSES = frozenset(
    {
        "permitted",
        "quality_blocked",
        "quality_unproven",
        "incomparable",
        "evidence_blocked",
        # Added by operator ruling 1 (2026-09-30) and the section 05 decision table.
        "no_claim_unstable",
        "no_baseline",
    }
)
REJECTION_REASONS = frozenset(
    {"evidence_invalid", "fingerprint_incomparable", "quality_failed", "quality_unproven"}
)
PERMITTED_EFFICIENCY_STATUSES = frozenset({"improvement", "regression", "within_range"})
METRIC_DIRECTIONS = frozenset({"lower_is_better", "higher_is_better", "target_range", "informational_only"})

EVALUATION_IDENTITY_FIELDS = (
    "suite_id",
    "suite_version",
    "dataset_or_fixture_hash",
    "scorer_id",
    "scorer_version",
    "harness_id",
    "harness_version",
    "split_or_holdout_class",
    "quality_floor_policy_id",
)

# Identity groups that feed the comparison digest. run_id, created_at, and the
# commit SHA stay outside it so that two runs of one configuration share a digest.
_CONFIG_GROUPS = ("subject_identity", "runtime_identity", "evaluation_identity", "execution_identity")


def precise_now_text() -> str:
    """UTC time with microseconds. Baseline selection orders by this value.

    ``utc_now_text`` has one-second resolution. Two runs in one second would tie,
    and the random run-ID suffix would pick the "latest" one at random.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    payload.pop("sha256", None)
    payload["sha256"] = sha256_json(payload)
    return payload


def _check_hash(payload: dict[str, Any], label: str, errors: list[str]) -> None:
    expected = payload.get("sha256")
    if not isinstance(expected, str) or not expected:
        errors.append(f"{label} is missing sha256.")
        return
    body = {key: value for key, value in payload.items() if key != "sha256"}
    if sha256_json(body) != expected:
        errors.append(f"{label} sha256 mismatch.")


def _check_required(payload: dict[str, Any], fields: tuple[str, ...], label: str, errors: list[str]) -> None:
    for field in fields:
        if field not in payload or payload[field] is None:
            errors.append(f"{label} is missing required field `{field}`.")


def _check_schema(payload: dict[str, Any], expected: str, errors: list[str]) -> bool:
    if not isinstance(payload, dict):
        errors.append(f"{expected} payload must be an object.")
        return False
    if payload.get("schema_version") != expected:
        errors.append(f"{expected} has an invalid schema_version.")
        return False
    return True


def _check_enum(payload: dict[str, Any], field: str, allowed: frozenset[str], label: str, errors: list[str]) -> None:
    if payload.get(field) not in allowed:
        errors.append(f"{label} has an invalid `{field}`: {payload.get(field)!r}.")


# --- EvaluationConfigFingerprint.v1 ---------------------------------------------------


def compute_config_digest(
    *,
    repo_id: str,
    workload_id: str,
    subject_kind: str,
    subject_identity: dict[str, Any],
    runtime_identity: dict[str, Any],
    evaluation_identity: dict[str, Any],
    execution_identity: dict[str, Any],
) -> str:
    return sha256_json(
        {
            "repo_id": repo_id,
            "workload_id": workload_id,
            "subject_kind": subject_kind,
            "subject_identity": subject_identity,
            "runtime_identity": runtime_identity,
            "evaluation_identity": evaluation_identity,
            "execution_identity": execution_identity,
        }
    )


def build_config_fingerprint(
    *,
    run_id: str,
    repo_id: str,
    workload_id: str,
    subject_kind: str,
    source_commit_sha: str,
    subject_identity: dict[str, Any],
    runtime_identity: dict[str, Any],
    evaluation_identity: dict[str, Any],
    execution_identity: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    config_digest = compute_config_digest(
        repo_id=repo_id,
        workload_id=workload_id,
        subject_kind=subject_kind,
        subject_identity=subject_identity,
        runtime_identity=runtime_identity,
        evaluation_identity=evaluation_identity,
        execution_identity=execution_identity,
    )
    return _seal(
        {
            "schema_version": FINGERPRINT_SCHEMA,
            "fingerprint_id": f"fingerprint:{workload_id}:{run_id}",
            "run_id": run_id,
            "repo_id": repo_id,
            "workload_id": workload_id,
            "subject_kind": subject_kind,
            "source_commit_sha": source_commit_sha,
            "subject_identity": subject_identity,
            "runtime_identity": runtime_identity,
            "evaluation_identity": evaluation_identity,
            "execution_identity": execution_identity,
            "config_digest": config_digest,
            "created_at": created_at or precise_now_text(),
        }
    )


def validate_config_fingerprint(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "EvaluationConfigFingerprint"
    if not _check_schema(payload, FINGERPRINT_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "fingerprint_id",
            "run_id",
            "repo_id",
            "workload_id",
            "subject_kind",
            "source_commit_sha",
            "config_digest",
            "created_at",
            *_CONFIG_GROUPS,
        ),
        label,
        errors,
    )
    _check_enum(payload, "subject_kind", SUBJECT_KINDS, label, errors)
    for group in _CONFIG_GROUPS:
        if group in payload and not isinstance(payload[group], dict):
            errors.append(f"{label} `{group}` must be an object.")
    evaluation = payload.get("evaluation_identity")
    if isinstance(evaluation, dict):
        for field in EVALUATION_IDENTITY_FIELDS:
            if evaluation.get(field) in (None, ""):
                errors.append(f"{label} evaluation_identity is missing `{field}`.")
    if not errors:
        expected = compute_config_digest(**{key: payload[key] for key in (
            "repo_id", "workload_id", "subject_kind", *_CONFIG_GROUPS
        )})
        if payload["config_digest"] != expected:
            errors.append(f"{label} config_digest is stale or tampered.")
    _check_hash(payload, label, errors)
    return errors


# --- QualityGateArtifact.v1 -----------------------------------------------------------


def evaluate_quality_floors(
    metric_results: dict[str, Any],
    quality_floors: dict[str, Any],
    sample_count: int,
) -> tuple[str, list[str]]:
    """Return ``(gate_status, failure_reasons)``.

    A floor is ``{"min": x}``, ``{"max": x}``, or ``{"equals": x}``. Missing floors,
    missing results, or zero samples are ``unproven``, never ``passed``.
    """
    if not quality_floors or sample_count < 1:
        return "unproven", ["No quality floors declared or no samples measured."]
    unproven: list[str] = []
    failed: list[str] = []
    for metric, floor in sorted(quality_floors.items()):
        if metric not in metric_results or not isinstance(metric_results[metric], (int, float)) or isinstance(
            metric_results[metric], bool
        ):
            unproven.append(f"No numeric result for floor `{metric}`.")
            continue
        value = metric_results[metric]
        if not isinstance(floor, dict) or len(floor) != 1 or next(iter(floor)) not in {"min", "max", "equals"}:
            return "invalid", [f"Floor for `{metric}` must be one of min, max, equals."]
        (op, bound), = floor.items()
        if op == "min" and value < bound:
            failed.append(f"`{metric}` {value} is below the minimum {bound}.")
        elif op == "max" and value > bound:
            failed.append(f"`{metric}` {value} is above the maximum {bound}.")
        elif op == "equals" and value != bound:
            failed.append(f"`{metric}` {value} does not equal {bound}.")
    if failed:
        return "failed", failed + unproven
    if unproven:
        return "unproven", unproven
    return "passed", []


def build_quality_gate_artifact(
    *,
    fingerprint: dict[str, Any],
    metric_results: dict[str, Any],
    quality_floors: dict[str, Any],
    sample_count: int,
    raw_evidence_refs: list[str],
    uncertainty_summary: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    gate_status, failure_reasons = evaluate_quality_floors(metric_results, quality_floors, sample_count)
    evaluation = fingerprint["evaluation_identity"]
    return _seal(
        {
            "schema_version": QUALITY_GATE_SCHEMA,
            "quality_gate_id": f"quality_gate:{fingerprint['workload_id']}:{fingerprint['run_id']}",
            "run_id": fingerprint["run_id"],
            "repo_id": fingerprint["repo_id"],
            "workload_id": fingerprint["workload_id"],
            "config_fingerprint_id": fingerprint["fingerprint_id"],
            "config_fingerprint_sha256": fingerprint["sha256"],
            "suite_id": evaluation["suite_id"],
            "suite_version": evaluation["suite_version"],
            "metric_results": metric_results,
            "quality_floors": quality_floors,
            "gate_status": gate_status,
            "failure_reasons": failure_reasons,
            "sample_count": sample_count,
            "uncertainty_summary": uncertainty_summary,
            "raw_evidence_refs": raw_evidence_refs,
            "created_at": created_at or utc_now_text(),
        }
    )


def validate_quality_gate_artifact(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "QualityGateArtifact"
    if not _check_schema(payload, QUALITY_GATE_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "quality_gate_id",
            "run_id",
            "repo_id",
            "workload_id",
            "config_fingerprint_id",
            "config_fingerprint_sha256",
            "suite_id",
            "suite_version",
            "metric_results",
            "quality_floors",
            "gate_status",
            "failure_reasons",
            "sample_count",
            "raw_evidence_refs",
            "created_at",
        ),
        label,
        errors,
    )
    _check_enum(payload, "gate_status", GATE_STATUSES, label, errors)
    if not errors:
        count = payload["sample_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"{label} sample_count must be a non-negative integer.")
        elif payload["gate_status"] in {"passed", "failed"}:
            # A stored verdict must match a fresh evaluation of its own floors.
            expected, _ = evaluate_quality_floors(payload["metric_results"], payload["quality_floors"], count)
            if expected != payload["gate_status"]:
                errors.append(f"{label} gate_status `{payload['gate_status']}` contradicts its floors (`{expected}`).")
        if payload["gate_status"] != "passed" and not payload["failure_reasons"]:
            errors.append(f"{label} with status `{payload['gate_status']}` must list failure_reasons.")
    _check_hash(payload, label, errors)
    return errors


# --- MetricVector.v1 ------------------------------------------------------------------


def build_metric_vector(
    *,
    fingerprint: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    sample_count: int,
    variance_or_uncertainty: dict[str, Any],
    measurement_scope: str,
    raw_evidence_refs: list[str],
    created_at: str | None = None,
) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": METRIC_VECTOR_SCHEMA,
            "metric_vector_id": f"metric_vector:{fingerprint['workload_id']}:{fingerprint['run_id']}",
            "run_id": fingerprint["run_id"],
            "workload_id": fingerprint["workload_id"],
            "config_fingerprint_id": fingerprint["fingerprint_id"],
            "config_fingerprint_sha256": fingerprint["sha256"],
            "metrics": metrics,
            "sample_count": sample_count,
            "variance_or_uncertainty": variance_or_uncertainty,
            "measurement_scope": measurement_scope,
            "raw_evidence_refs": raw_evidence_refs,
            "created_at": created_at or utc_now_text(),
        }
    )


def validate_metric_vector(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "MetricVector"
    if not _check_schema(payload, METRIC_VECTOR_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "metric_vector_id",
            "run_id",
            "workload_id",
            "config_fingerprint_id",
            "config_fingerprint_sha256",
            "metrics",
            "sample_count",
            "variance_or_uncertainty",
            "measurement_scope",
            "raw_evidence_refs",
            "created_at",
        ),
        label,
        errors,
    )
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        if not metrics:
            errors.append(f"{label} must declare at least one metric.")
        for name, entry in sorted(metrics.items()):
            if not isinstance(entry, dict):
                errors.append(f"{label} metric `{name}` must be an object.")
                continue
            value = entry.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{label} metric `{name}` needs a numeric value.")
            if entry.get("direction") not in METRIC_DIRECTIONS:
                errors.append(f"{label} metric `{name}` needs a declared direction.")
            if base_metric_name(name) in ENERGY_METRICS | {"joules_per_successful_task"}:
                if entry.get("scope") not in ENERGY_SCOPES:
                    errors.append(f"{label} energy metric `{name}` needs a declared measurement scope.")
    elif metrics is not None:
        errors.append(f"{label} metrics must be an object.")
    _check_hash(payload, label, errors)
    return errors


# --- QualityEfficiencyComparison.v1 ---------------------------------------------------


def build_quality_efficiency_comparison(
    *,
    run_id: str,
    workload_id: str,
    candidate_fingerprint_id: str,
    baseline_fingerprint_id: str | None,
    candidate_run_id: str,
    baseline_run_id: str | None,
    quality_status: str,
    comparability_status: str,
    efficiency_status: str,
    claim_status: str,
    comparison_dimensions: dict[str, Any],
    metric_deltas: dict[str, Any],
    blocked_reasons: list[str],
    baseline_rejections: list[dict[str, Any]] | None = None,
    primary_metric: str = "median_ms",
    created_at: str | None = None,
) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": COMPARISON_SCHEMA,
            "comparison_id": f"comparison:{workload_id}:{run_id}",
            "run_id": run_id,
            "workload_id": workload_id,
            "candidate_fingerprint_id": candidate_fingerprint_id,
            "baseline_fingerprint_id": baseline_fingerprint_id,
            "quality_status": quality_status,
            "comparability_status": comparability_status,
            "efficiency_status": efficiency_status,
            "claim_status": claim_status,
            "comparison_dimensions": comparison_dimensions,
            "metric_deltas": metric_deltas,
            "blocked_reasons": blocked_reasons,
            "baseline_rejections": baseline_rejections or [],
            "primary_metric": primary_metric,
            "baseline_run_id": baseline_run_id,
            "candidate_run_id": candidate_run_id,
            "created_at": created_at or utc_now_text(),
        }
    )


def validate_quality_efficiency_comparison(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "QualityEfficiencyComparison"
    if not _check_schema(payload, COMPARISON_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "comparison_id",
            "run_id",
            "workload_id",
            "candidate_fingerprint_id",
            "candidate_run_id",
            "quality_status",
            "comparability_status",
            "efficiency_status",
            "claim_status",
            "comparison_dimensions",
            "metric_deltas",
            "blocked_reasons",
            "created_at",
        ),
        label,
        errors,
    )
    _check_enum(payload, "quality_status", GATE_STATUSES, label, errors)
    _check_enum(payload, "comparability_status", COMPARABILITY_STATUSES, label, errors)
    _check_enum(payload, "efficiency_status", EFFICIENCY_STATUSES, label, errors)
    _check_enum(payload, "claim_status", CLAIM_STATUSES, label, errors)
    rejections = payload.get("baseline_rejections", [])
    if not isinstance(rejections, list) or any(
        not isinstance(item, dict) or item.get("reason") not in REJECTION_REASONS for item in rejections
    ):
        errors.append(f"{label} baseline_rejections must list entries with a known reason.")
    if not errors:
        errors.extend(_check_claim_consistency(payload, label))
    _check_hash(payload, label, errors)
    return errors


def _check_claim_consistency(payload: dict[str, Any], label: str) -> list[str]:
    """Reject a comparison that names improvement or regression without its gates."""
    errors: list[str] = []
    claims_direction = payload["efficiency_status"] in {"improvement", "regression"}
    if claims_direction or payload["claim_status"] in {"permitted", "no_claim_unstable"}:
        if payload["quality_status"] != "passed":
            errors.append(f"{label} claims a result without a passed quality gate.")
        if payload["comparability_status"] != "comparable":
            errors.append(f"{label} claims a result without a comparable baseline.")
        if not payload.get("baseline_fingerprint_id"):
            errors.append(f"{label} claims a result without a baseline fingerprint.")
    if payload["claim_status"] == "permitted" and payload["efficiency_status"] not in PERMITTED_EFFICIENCY_STATUSES:
        errors.append(f"{label} is permitted but efficiency_status is `{payload['efficiency_status']}`.")
    if payload["claim_status"] == "no_claim_unstable" and payload["efficiency_status"] != "unstable":
        errors.append(f"{label} is no_claim_unstable but efficiency_status is not unstable.")
    if payload["efficiency_status"] == "unstable" and payload["claim_status"] != "no_claim_unstable":
        errors.append(f"{label} names unstable but claim_status is not no_claim_unstable.")
    if claims_direction and payload["claim_status"] != "permitted":
        errors.append(f"{label} names `{payload['efficiency_status']}` while claim_status is not permitted.")
    if payload["claim_status"] == "quality_blocked" and payload["quality_status"] != "failed":
        errors.append(f"{label} is quality_blocked but quality_status is not failed.")
    if payload["claim_status"] == "quality_unproven" and payload["quality_status"] != "unproven":
        errors.append(f"{label} is quality_unproven but quality_status is not unproven.")
    if payload["claim_status"] == "incomparable" and payload["comparability_status"] != "incomparable":
        errors.append(f"{label} is incomparable but comparability_status is not incomparable.")
    if payload["claim_status"] != "permitted" and not payload["blocked_reasons"]:
        errors.append(f"{label} blocks the claim but lists no blocked_reasons.")
    return errors


# --- Cross-artifact linkage -----------------------------------------------------------


def check_evidence_linkage(
    fingerprint: dict[str, Any],
    quality_gate: dict[str, Any] | None,
    metric_vector: dict[str, Any] | None,
) -> list[str]:
    """Return linkage errors. Any error means the claim is ``evidence_blocked``.

    A missing quality gate is not a linkage error. The claim gate maps it to
    ``quality_unproven``.
    """
    errors: list[str] = []
    for label, artifact in (("QualityGateArtifact", quality_gate), ("MetricVector", metric_vector)):
        if artifact is None:
            continue
        if artifact.get("config_fingerprint_id") != fingerprint.get("fingerprint_id"):
            errors.append(f"{label} references a different config fingerprint id.")
        if artifact.get("config_fingerprint_sha256") != fingerprint.get("sha256"):
            errors.append(f"{label} references a different config fingerprint digest.")
        if artifact.get("run_id") != fingerprint.get("run_id"):
            errors.append(f"{label} run_id does not match the fingerprint run_id.")
    return errors
