"""Configuration comparability and baseline matching for BDS-ERA-EVAL-v0.1 (WP02).

This module reads fingerprints only. It does not touch the legacy efficiency
baseline path in ``era_core.efficiency``. Any doubt fails closed to ``unknown``
or ``incomparable``. Neither one is an improvement or a regression.
"""

from __future__ import annotations

from typing import Any, Iterable

from era_core.eval_contracts import EVALUATION_IDENTITY_FIELDS

# Dimensions that every baseline match must satisfy (plan section 05).
DEFAULT_REQUIRED_DIMENSIONS = (
    "repo_id",
    "workload_id",
    "subject_kind",
    "evaluation.suite_id",
    "evaluation.suite_version",
    "evaluation.dataset_or_fixture_hash",
    "evaluation.quality_floor_policy_id",
)

_TOP_LEVEL_DIMENSIONS = frozenset({"repo_id", "workload_id", "subject_kind", "source.commit_sha"})
_EXECUTION_DIMENSIONS = frozenset(
    {
        "hardware_fingerprint",
        "os_runtime_version",
        "concurrency",
        "batch_size",
        "network_mode",
        "resource_policy_id",
        "energy_scope",
        "sandbox",
        "sandbox_backend",
        "network",
        "target_filesystem",
    }
)
# ``subject.*`` and ``runtime.*`` keys are free-form because they depend on the subject kind.
_FREE_FORM_PREFIXES = ("subject.", "runtime.")


def flatten_dimensions(fingerprint: dict[str, Any]) -> dict[str, Any]:
    """Return the flat ``dimension -> value`` map that comparison uses."""
    flat: dict[str, Any] = {
        "repo_id": fingerprint.get("repo_id"),
        "workload_id": fingerprint.get("workload_id"),
        "subject_kind": fingerprint.get("subject_kind"),
        "source.commit_sha": fingerprint.get("source_commit_sha"),
    }
    for prefix, group in (
        ("subject", "subject_identity"),
        ("runtime", "runtime_identity"),
        ("evaluation", "evaluation_identity"),
        ("execution", "execution_identity"),
    ):
        for key, value in (fingerprint.get(group) or {}).items():
            flat[f"{prefix}.{key}"] = value
    return flat


def is_known_dimension(name: str) -> bool:
    if name in _TOP_LEVEL_DIMENSIONS:
        return True
    if name.startswith("evaluation."):
        return name.removeprefix("evaluation.") in EVALUATION_IDENTITY_FIELDS
    if name.startswith("execution."):
        return name.removeprefix("execution.") in _EXECUTION_DIMENSIONS
    return name.startswith(_FREE_FORM_PREFIXES) and len(name.split(".", 1)[1]) > 0


def compare_fingerprints(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    required_dimensions: Iterable[str] = DEFAULT_REQUIRED_DIMENSIONS,
    non_binding_dimensions: Iterable[str] = (),
) -> dict[str, Any]:
    """Compare two fingerprints on the required dimensions.

    ``non_binding_dimensions`` is the only way to waive a dimension. The manifest
    must declare it. A required dimension that is unrecognized, or that is absent
    from either side, gives ``unknown``. A required dimension with two different
    values gives ``incomparable``. ``incomparable`` outranks ``unknown``.
    """
    waived = set(non_binding_dimensions)
    flat_candidate = flatten_dimensions(candidate)
    flat_baseline = flatten_dimensions(baseline)
    dimensions: dict[str, Any] = {}
    mismatches: list[str] = []
    unknown: list[str] = []

    for name in sorted(set(required_dimensions) - waived):
        if not is_known_dimension(name):
            unknown.append(f"`{name}` is not a recognized comparison dimension.")
            dimensions[name] = {"result": "unknown"}
            continue
        left, right = flat_candidate.get(name), flat_baseline.get(name)
        if left is None or right is None:
            unknown.append(f"`{name}` is missing from the {'candidate' if left is None else 'baseline'}.")
            dimensions[name] = {"result": "unknown", "candidate": left, "baseline": right}
        elif left != right:
            mismatches.append(f"`{name}` differs: candidate {left!r}, baseline {right!r}.")
            dimensions[name] = {"result": "mismatch", "candidate": left, "baseline": right}
        else:
            dimensions[name] = {"result": "match", "value": left}

    status = "incomparable" if mismatches else "unknown" if unknown else "comparable"
    return {
        "comparability_status": status,
        "comparison_dimensions": dimensions,
        "non_binding_dimensions": sorted(waived),
        "blocked_reasons": mismatches + unknown,
    }


def select_baseline(
    candidate: dict[str, Any],
    prior_fingerprints: Iterable[dict[str, Any]],
    required_dimensions: Iterable[str] = DEFAULT_REQUIRED_DIMENSIONS,
    non_binding_dimensions: Iterable[str] = (),
) -> dict[str, Any]:
    """Pick the latest prior fingerprint that is comparable to the candidate.

    A prior run for the same repo and workload is not a baseline unless it is
    comparable. Rejected runs stay in the result, so the review can show why.
    """
    required = tuple(required_dimensions)
    rejected: list[dict[str, Any]] = []
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for prior in prior_fingerprints:
        if prior.get("run_id") == candidate.get("run_id"):
            continue
        result = compare_fingerprints(candidate, prior, required, non_binding_dimensions)
        if result["comparability_status"] == "comparable":
            matches.append((prior, result))
        else:
            rejected.append(
                {
                    "fingerprint_id": prior.get("fingerprint_id"),
                    "run_id": prior.get("run_id"),
                    "comparability_status": result["comparability_status"],
                    "blocked_reasons": result["blocked_reasons"],
                }
            )
    if not matches:
        return {
            "baseline_found": False,
            "baseline_fingerprint_id": None,
            "baseline_run_id": None,
            "comparison": None,
            "rejected": rejected,
        }
    chosen, comparison = max(matches, key=lambda item: (item[0].get("created_at", ""), item[0].get("run_id", "")))
    return {
        "baseline_found": True,
        "baseline_fingerprint_id": chosen["fingerprint_id"],
        "baseline_run_id": chosen["run_id"],
        "comparison": comparison,
        "rejected": rejected,
    }
