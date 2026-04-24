from __future__ import annotations

from pathlib import Path
from typing import Any

from era_core.hashing import write_json


def write_centipede_export(
    *,
    run_artifact: dict[str, Any],
    selection_artifact: dict[str, Any] | None,
    evidence_bundles: dict[str, dict[str, Any]],
    findings: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    bundle = {
        "schema_version": "CentipedeExportBundle.v1",
        "run_id": run_artifact["run_id"],
        "repo_id": run_artifact["repo_id"],
        "commit_sha": run_artifact["commit_sha"],
        "lane_results": [
            {
                "lane": lane,
                "run_status": run_artifact["status"],
                "read_only_invariant_status": run_artifact["read_only_invariant_status"],
            }
            for lane in evidence_bundles.keys()
        ],
        "selection": (
            {
                "mode": selection_artifact["mode"],
                "selection_method": selection_artifact["selection_method"],
                "selection_safety_class": selection_artifact["selection_safety_class"],
            }
            if selection_artifact is not None
            else None
        ),
        "evidence_bundle_refs": run_artifact["evidence_bundle_refs"],
        "finding_ids": [item["finding_id"] for item in findings.get("era_findings", [])],
        "projection_candidates": [
            item["finding_id"]
            for item in findings.get("era_findings", [])
            if item["finding_type"] in {"accuracy_gate_failed", "harmful_redundancy_candidate"}
        ],
    }
    write_json(output_path, bundle)
    return bundle
