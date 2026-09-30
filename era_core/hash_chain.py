from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.artifact_paths import utc_now_text
from era_core.hashing import sha256_path


def _relative_path(run_root: Path, path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    try:
        return path.relative_to(run_root).as_posix()
    except ValueError:
        return path.as_posix()


def _collect_file_entries(run_root: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file() or path.name == "hashes.json":
            continue
        entries.append(
            {
                "path": path.relative_to(run_root).as_posix(),
                "sha256": sha256_path(path),
            }
        )
    return entries


def build_evidence_hash_chain(
    *,
    run_id: str,
    run_root: Path,
    evidence_bundles: dict[str, dict[str, Any]],
    findings_bundle: dict[str, Any],
    review_path: Path,
) -> dict[str, Any]:
    raw_artifacts: list[dict[str, Any]] = []
    normalized_results: list[dict[str, Any]] = []
    for lane, bundle in sorted(evidence_bundles.items()):
        for artifact in bundle.get("tool_raw_artifacts", []):
            raw_artifacts.append(
                {
                    "raw_artifact_id": artifact["raw_artifact_id"],
                    "lane": lane,
                    "command_id": artifact["command_id"],
                    "artifact_kind": artifact["artifact_kind"],
                    "path": _relative_path(run_root, artifact.get("path")),
                    "sha256": artifact["sha256"],
                }
            )
        for normalized in bundle.get("tool_normalized_results", []):
            normalized_results.append(
                {
                    "normalized_result_id": normalized["normalized_result_id"],
                    "lane": lane,
                    "raw_artifact_refs": normalized.get("raw_artifact_refs", []),
                    "sha256": normalized["sha256"],
                }
            )

    lane_finding_drafts = [
        {
            "draft_id": draft["draft_id"],
            "lane": draft["lane"],
            "evidence_refs": draft.get("evidence_refs", []),
            "sha256": draft["sha256"],
        }
        for draft in findings_bundle.get("lane_finding_drafts", [])
    ]
    era_findings = [
        {
            "finding_id": finding["finding_id"],
            "lane": finding["lane"],
            "evidence_refs": finding.get("evidence_refs", []),
            "raw_evidence_refs": finding.get("raw_evidence_refs", []),
            "raw_evidence_hashes": finding.get("raw_evidence_hashes", []),
            "sha256": finding["sha256"],
        }
        for finding in findings_bundle.get("era_findings", [])
    ]
    era_scores = [
        {
            "score_id": score["score_id"],
            "scope": score["scope"],
            "lane": score.get("lane"),
            "sha256": score["sha256"],
        }
        for score in findings_bundle.get("era_scores", [])
    ]

    evaluation_artifacts = [
        {"workload_id": workload_id, "kind": kind, "path": entry[kind]["path"], "sha256": entry[kind]["sha256"]}
        for workload_id, entry in sorted(
            ((evidence_bundles.get("efficiency") or {}).get("evaluation_evidence_refs") or {}).items()
        )
        for kind in ("fingerprint", "quality_gate", "metric_vector", "judge_audit", "isolation_receipt", "comparison")
        if entry.get(kind)
    ]
    chain = {
        "schema_version": "ERAEvidenceHashChain.v1",
        "run_id": run_id,
        "raw_artifacts": raw_artifacts,
        "normalized_results": normalized_results,
        "lane_finding_drafts": lane_finding_drafts,
        "era_findings": era_findings,
        "era_scores": era_scores,
        "findings_bundle": {
            "path": "findings.json",
            "sha256": findings_bundle["sha256"],
        },
        "review_artifact": {
            "path": _relative_path(run_root, str(review_path)),
            "sha256": sha256_path(review_path),
        },
        "created_at": utc_now_text(),
    }
    if evaluation_artifacts:
        chain["evaluation_artifacts"] = evaluation_artifacts
        export_path = run_root / "evaluation_export.json"
        if export_path.exists():
            embedded = json.loads(export_path.read_text(encoding="utf-8")).get("sha256")
            chain["evaluation_export"] = {"path": "evaluation_export.json", "sha256": embedded}
    return chain


def build_hash_manifest(
    *,
    run_id: str,
    run_root: Path,
    evidence_bundles: dict[str, dict[str, Any]],
    findings_bundle: dict[str, Any],
    review_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "ERAHashManifest.v1",
        "run_id": run_id,
        "entries": _collect_file_entries(run_root),
        "evidence_hash_chain": build_evidence_hash_chain(
            run_id=run_id,
            run_root=run_root,
            evidence_bundles=evidence_bundles,
            findings_bundle=findings_bundle,
            review_path=review_path,
        ),
        "created_at": utc_now_text(),
    }
