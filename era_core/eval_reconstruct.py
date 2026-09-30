"""Rebuild an evaluation claim from artifacts on disk (WP06, GATE-06).

The rebuild reads only files. It calls no model, provider, or network. It must
give the same claim as the one the run stored. A difference means the stored
receipt cannot be reproduced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_claims import decide_claim, load_prior_evidence, select_eligible_baseline
from era_core.eval_lane import eval_policy, primary_metric, required_dimensions, sample_policy, workload_dirname

COMPARED_FIELDS = (
    "isolation_status",
    "quality_status",
    "comparability_status",
    "efficiency_status",
    "claim_status",
    "baseline_run_id",
    "baseline_fingerprint_id",
)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def reconstruct_claim(run_dir: Path, workload_id: str, from_snapshot: bool = False) -> dict[str, Any]:
    """Recompute the decision for one workload from the run directory alone.

    Prior runs count only when they were created before the candidate. A later
    run cannot change an earlier claim.

    With ``from_snapshot`` the baseline is the run's own baseline snapshot and no
    sibling run folder is read. That works after old runs are archived. It cannot
    re-check which other priors were rejected, so it proves the claim given the
    recorded baseline, not the choice of baseline.
    """
    directory = run_dir / "evidence" / "efficiency" / "eval" / workload_dirname(workload_id)
    candidate = {
        "workload_id": workload_id,
        "fingerprint": _load(directory / "fingerprint.json"),
        "quality_gate": _load(directory / "quality_gate.json"),
        "metric_vector": _load(directory / "metric_vector.json"),
        "problems": [],
    }
    isolation = _load(directory / "isolation_receipt.json")
    gate = candidate["quality_gate"]
    candidate["quality_status"] = gate["gate_status"] if gate else "invalid"
    if candidate["fingerprint"] is None:
        candidate["problems"] = ["Fingerprint is missing."]

    bundle = _load(run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json") or {}
    workload = next(
        (w for w in (bundle.get("workload_manifest") or {}).get("workloads", []) if w.get("workload_id") == workload_id),
        {},
    )
    policy = eval_policy(workload) or {}
    selection: dict[str, Any] = {"baseline": None, "comparison": None, "rejected": [], "considered": 0}
    snapshot = _load(directory / "baseline_snapshot.json") if from_snapshot else None
    if from_snapshot and snapshot is not None and candidate["fingerprint"] is not None:
        prior = {
            "run_id": snapshot["baseline_run_id"],
            "fingerprint": snapshot["fingerprint"],
            "quality_gate": snapshot["quality_gate"],
            "metric_vector": snapshot["metric_vector"],
        }
        selection = select_eligible_baseline(
            candidate["fingerprint"], [prior], required_dimensions(policy), tuple(policy.get("non_binding_dimensions") or ())
        )
    elif candidate["fingerprint"] is not None:
        cutoff = candidate["fingerprint"]["created_at"]
        priors = [
            prior
            for prior in load_prior_evidence(run_dir.parent, run_dir.name, workload_id, workload_dirname(workload_id))
            if (prior["fingerprint"] or {}).get("created_at", "") < cutoff
        ]
        selection = select_eligible_baseline(
            candidate["fingerprint"],
            priors,
            required_dimensions(policy),
            tuple(policy.get("non_binding_dimensions") or ()),
        )
    return decide_claim(
        candidate=candidate,
        selection=selection,
        regression_threshold_pct=float(workload.get("regression_threshold_pct", 10.0)),
        improvement_threshold_pct=float(workload.get("improvement_threshold_pct", 10.0)),
        primary_metric=primary_metric(policy),
        min_samples=int(sample_policy(policy).get("min_samples", 0)),
        require_ci_separation=bool(sample_policy(policy).get("require_ci_separation", False)),
        isolation_status=(isolation or {}).get("status", "not_required"),
    ) | {"baseline_run_id": (selection["baseline"] or {}).get("run_id"),
         "baseline_fingerprint_id": ((selection["baseline"] or {}).get("fingerprint") or {}).get("fingerprint_id")}


def compare_to_stored(run_dir: Path, workload_id: str, from_snapshot: bool = False) -> dict[str, Any]:
    """Return ``{"match": bool, "differences": [...], "reconstructed": {...}}``."""
    stored = _load(run_dir / "evidence" / "efficiency" / "eval" / workload_dirname(workload_id) / "comparison.json")
    rebuilt = reconstruct_claim(run_dir, workload_id, from_snapshot=from_snapshot)
    if stored is None:
        return {"match": False, "differences": ["Stored comparison is missing."], "reconstructed": rebuilt}
    differences = [
        f"{field}: stored {stored.get(field)!r}, reconstructed {rebuilt.get(field)!r}"
        for field in COMPARED_FIELDS
        if stored.get(field) != rebuilt.get(field)
    ]
    if stored.get("primary_metric", "median_ms") != rebuilt.get("primary_metric"):
        differences.append(
            f"primary_metric: stored {stored.get('primary_metric')!r}, reconstructed {rebuilt.get('primary_metric')!r}"
        )
    for name in sorted(set(stored.get("metric_deltas") or {}) | set(rebuilt.get("metric_deltas") or {})):
        stored_delta = ((stored.get("metric_deltas") or {}).get(name) or {}).get("delta_pct")
        rebuilt_delta = ((rebuilt.get("metric_deltas") or {}).get(name) or {}).get("delta_pct")
        if stored_delta != rebuilt_delta:
            differences.append(f"{name} delta_pct: stored {stored_delta!r}, reconstructed {rebuilt_delta!r}")
    return {"match": not differences, "differences": differences, "reconstructed": rebuilt}
