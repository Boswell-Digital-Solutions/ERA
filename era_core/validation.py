from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_validation import validate_eval_evidence
from era_core.hashing import sha256_json, sha256_path
from era_integrations.centipede_export import validate_centipede_export_bundle


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_command_artifacts(
    *,
    bundle: dict[str, Any],
    errors: list[str],
) -> None:
    for result in bundle["command_results"]:
        if result["status"] in {"skipped", "blocked_by_missing_tool"}:
            continue
        stdout_value = result.get("stdout_path")
        stderr_value = result.get("stderr_path")
        if not stdout_value:
            errors.append(f"Missing stdout artifact for {result['command_id']}")
        if not stderr_value:
            errors.append(f"Missing stderr artifact for {result['command_id']}")
            continue

        stdout_path = Path(stdout_value)
        stderr_path = Path(stderr_value)
        if not stdout_path.exists():
            errors.append(f"Missing stdout artifact for {result['command_id']}")
        if not stderr_path.exists():
            errors.append(f"Missing stderr artifact for {result['command_id']}")
        if stdout_path.exists() and sha256_path(stdout_path) != result["stdout_sha256"]:
            errors.append(f"stdout hash mismatch for {result['command_id']}")
        if stderr_path.exists() and sha256_path(stderr_path) != result["stderr_sha256"]:
            errors.append(f"stderr hash mismatch for {result['command_id']}")


def _relative_to_run(run_dir: Path, path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_embedded_hash(payload: dict[str, Any], label: str, errors: list[str]) -> None:
    expected = payload.get("sha256")
    if not expected:
        errors.append(f"{label} is missing sha256.")
        return
    comparable = dict(payload)
    comparable.pop("sha256", None)
    actual = sha256_json(comparable)
    if actual != expected:
        errors.append(f"{label} embedded sha256 mismatch.")


def _validate_finding_contracts(
    *,
    findings: dict[str, Any],
    evidence_bundles: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    drafts = findings.get("lane_finding_drafts")
    era_findings = findings.get("era_findings")
    era_scores = findings.get("era_scores")
    if not isinstance(drafts, list):
        errors.append("findings.json lane_finding_drafts must be a list.")
        drafts = []
    if not isinstance(era_findings, list):
        errors.append("findings.json era_findings must be a list.")
        era_findings = []
    if not isinstance(era_scores, list):
        errors.append("findings.json era_scores must be a list.")
        era_scores = []

    normalized_result_ids = {
        item["normalized_result_id"]
        for bundle in evidence_bundles.values()
        for item in bundle.get("tool_normalized_results", [])
    }
    draft_ids = {item.get("draft_id") for item in drafts if isinstance(item, dict)}

    for draft in drafts:
        if draft.get("schema_version") != "LaneFindingDraft.v1":
            errors.append(f"Draft {draft.get('draft_id', 'unknown')} has an invalid schema_version.")
        if "risk_level" not in draft or "confidence" not in draft:
            errors.append(f"Draft {draft.get('draft_id', 'unknown')} is missing risk_level or confidence.")
        for ref in draft.get("evidence_refs", []):
            if ref not in normalized_result_ids:
                errors.append(f"Draft {draft.get('draft_id', 'unknown')} references missing normalized result {ref}.")

    for finding in era_findings:
        if finding.get("schema_version") != "ERAFinding.v1":
            errors.append(f"Finding {finding.get('finding_id', 'unknown')} has an invalid schema_version.")
        if "risk_level" not in finding or "confidence" not in finding:
            errors.append(f"Finding {finding.get('finding_id', 'unknown')} is missing risk_level or confidence.")
        if finding.get("safe_to_autofix") is not False:
            errors.append(f"Finding {finding.get('finding_id', 'unknown')} must keep safe_to_autofix=false.")
        for ref in finding.get("evidence_refs", []):
            if ref not in normalized_result_ids and ref not in draft_ids:
                errors.append(f"Finding {finding.get('finding_id', 'unknown')} references missing evidence {ref}.")

    scopes = {item.get("scope") for item in era_scores if isinstance(item, dict)}
    if "overall" not in scopes:
        errors.append("findings.json must include an overall ERAScore.v1 entry.")
    for score in era_scores:
        if score.get("schema_version") != "ERAScore.v1":
            errors.append(f"Score {score.get('score_id', 'unknown')} has an invalid schema_version.")
        if score.get("scope") not in {"lane", "overall"}:
            errors.append(f"Score {score.get('score_id', 'unknown')} has invalid scope {score.get('scope')}.")
        for field in (
            "classification",
            "command_status_counts",
            "risk_counts",
            "confidence_counts",
            "evidence_strength_counts",
        ):
            if field not in score:
                errors.append(f"Score {score.get('score_id', 'unknown')} is missing {field}.")


def _validate_hash_chain(
    *,
    run_dir: Path,
    hashes: dict[str, Any],
    findings: dict[str, Any],
    evidence_bundles: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    chain = hashes.get("evidence_hash_chain")
    if not isinstance(chain, dict):
        errors.append("hashes.json is missing evidence_hash_chain.")
        return
    if chain.get("schema_version") != "ERAEvidenceHashChain.v1":
        errors.append("evidence_hash_chain has invalid schema_version.")

    raw_artifact_map: dict[str, dict[str, Any]] = {}
    normalized_map: dict[str, dict[str, Any]] = {}
    for lane, bundle in evidence_bundles.items():
        _validate_embedded_hash(bundle, f"{lane} evidence bundle", errors)
        for raw in bundle.get("tool_raw_artifacts", []):
            raw_artifact_map[raw["raw_artifact_id"]] = raw
        for normalized in bundle.get("tool_normalized_results", []):
            _validate_embedded_hash(normalized, f"Normalized result {normalized.get('normalized_result_id', 'unknown')}", errors)
            normalized_map[normalized["normalized_result_id"]] = normalized

    _validate_embedded_hash(findings, "findings.json", errors)
    draft_map = {item["draft_id"]: item for item in findings.get("lane_finding_drafts", [])}
    finding_map = {item["finding_id"]: item for item in findings.get("era_findings", [])}
    score_map = {item["score_id"]: item for item in findings.get("era_scores", [])}
    for draft in draft_map.values():
        _validate_embedded_hash(draft, f"Draft {draft.get('draft_id', 'unknown')}", errors)
    for finding in finding_map.values():
        _validate_embedded_hash(finding, f"Finding {finding.get('finding_id', 'unknown')}", errors)
    for score in score_map.values():
        _validate_embedded_hash(score, f"Score {score.get('score_id', 'unknown')}", errors)

    raw_chain = {item.get("raw_artifact_id"): item for item in chain.get("raw_artifacts", [])}
    normalized_chain = {item.get("normalized_result_id"): item for item in chain.get("normalized_results", [])}
    draft_chain = {item.get("draft_id"): item for item in chain.get("lane_finding_drafts", [])}
    finding_chain = {item.get("finding_id"): item for item in chain.get("era_findings", [])}
    score_chain = {item.get("score_id"): item for item in chain.get("era_scores", [])}

    for raw_id, raw in raw_artifact_map.items():
        chain_entry = raw_chain.get(raw_id)
        if chain_entry is None:
            errors.append(f"Evidence hash chain missing raw artifact {raw_id}.")
            continue
        if chain_entry.get("sha256") != raw.get("sha256"):
            errors.append(f"Evidence hash chain has stale raw artifact hash for {raw_id}.")
        if chain_entry.get("path") != _relative_to_run(run_dir, raw.get("path")):
            errors.append(f"Evidence hash chain has stale raw artifact path for {raw_id}.")
    for raw_id in raw_chain:
        if raw_id not in raw_artifact_map:
            errors.append(f"Evidence hash chain references missing raw artifact {raw_id}.")

    for normalized_id, normalized in normalized_map.items():
        chain_entry = normalized_chain.get(normalized_id)
        if chain_entry is None:
            errors.append(f"Evidence hash chain missing normalized result {normalized_id}.")
            continue
        if chain_entry.get("sha256") != normalized.get("sha256"):
            errors.append(f"Evidence hash chain has stale normalized result hash for {normalized_id}.")
        if chain_entry.get("raw_artifact_refs") != normalized.get("raw_artifact_refs", []):
            errors.append(f"Evidence hash chain has stale raw refs for normalized result {normalized_id}.")
        for ref in normalized.get("raw_artifact_refs", []):
            if ref not in raw_artifact_map:
                errors.append(f"Normalized result {normalized_id} references missing raw artifact {ref}.")
    for normalized_id in normalized_chain:
        if normalized_id not in normalized_map:
            errors.append(f"Evidence hash chain references missing normalized result {normalized_id}.")

    for draft_id, draft in draft_map.items():
        chain_entry = draft_chain.get(draft_id)
        if chain_entry is None:
            errors.append(f"Evidence hash chain missing draft {draft_id}.")
            continue
        if chain_entry.get("sha256") != draft.get("sha256"):
            errors.append(f"Evidence hash chain has stale draft hash for {draft_id}.")
        if chain_entry.get("evidence_refs") != draft.get("evidence_refs", []):
            errors.append(f"Evidence hash chain has stale evidence refs for draft {draft_id}.")
    for draft_id in draft_chain:
        if draft_id not in draft_map:
            errors.append(f"Evidence hash chain references missing draft {draft_id}.")

    for finding_id, finding in finding_map.items():
        if finding.get("evidence_strength") not in {"none", "advisory_only", "blocked", "unproven"}:
            if not finding.get("raw_evidence_refs") or not finding.get("raw_evidence_hashes"):
                errors.append(f"Finding {finding_id} requires raw_evidence_refs and raw_evidence_hashes.")
        if finding.get("finding_type") == "clear_issue" or finding.get("classification") == "clear_issue":
            if not finding.get("raw_evidence_refs") or not finding.get("raw_evidence_hashes"):
                errors.append(f"clear_issue finding {finding_id} requires raw_evidence_refs and raw_evidence_hashes.")
        chain_entry = finding_chain.get(finding_id)
        if chain_entry is None:
            errors.append(f"Evidence hash chain missing finding {finding_id}.")
            continue
        if chain_entry.get("sha256") != finding.get("sha256"):
            errors.append(f"Evidence hash chain has stale finding hash for {finding_id}.")
        for field in ("evidence_refs", "raw_evidence_refs", "raw_evidence_hashes"):
            if chain_entry.get(field) != finding.get(field, []):
                errors.append(f"Evidence hash chain has stale {field} for finding {finding_id}.")
    for finding_id in finding_chain:
        if finding_id not in finding_map:
            errors.append(f"Evidence hash chain references missing finding {finding_id}.")

    for score_id, score in score_map.items():
        chain_entry = score_chain.get(score_id)
        if chain_entry is None:
            errors.append(f"Evidence hash chain missing score {score_id}.")
            continue
        if chain_entry.get("sha256") != score.get("sha256"):
            errors.append(f"Evidence hash chain has stale score hash for {score_id}.")
    for score_id in score_chain:
        if score_id not in score_map:
            errors.append(f"Evidence hash chain references missing score {score_id}.")

    findings_ref = chain.get("findings_bundle", {})
    if findings_ref.get("sha256") != findings.get("sha256"):
        errors.append("Evidence hash chain has stale findings bundle hash.")
    review_ref = chain.get("review_artifact", {})
    review_path = run_dir / review_ref.get("path", "review.md")
    if not review_path.exists():
        errors.append("Evidence hash chain references missing review artifact.")
    elif review_ref.get("sha256") != sha256_path(review_path):
        errors.append("Evidence hash chain has stale review artifact hash.")

    review_text = review_path.read_text(encoding="utf-8") if review_path.exists() else ""
    review_hashes = [findings.get("sha256")]
    review_hashes.extend(bundle.get("sha256") for bundle in evidence_bundles.values())
    review_hashes.extend(item.get("sha256") for item in finding_map.values())
    review_hashes.extend(item.get("sha256") for item in score_map.values())
    for hash_value in [item for item in review_hashes if item]:
        if hash_value not in review_text:
            errors.append(f"review.md is missing hash reference {hash_value}.")


def _validate_selection_artifact(
    *,
    selection: dict[str, Any],
    run_artifact: dict[str, Any],
    errors: list[str],
) -> None:
    required_fields = {
        "schema_version",
        "run_id",
        "repo_id",
        "baseline_ref",
        "baseline_commit",
        "current_commit",
        "mode",
        "selection_level",
        "selection_method",
        "selection_safety_class",
        "changed_files",
        "changed_symbols",
        "candidate_tests",
        "selected_tests",
        "excluded_tests",
        "full_run_required",
        "full_run_executed",
        "fallback_reason",
        "coverage_snapshot_ref",
        "manifest_mapping_ref",
        "rts_tool_name",
        "rts_tool_version",
        "selection_rationale",
        "created_at",
    }
    missing = sorted(field for field in required_fields if field not in selection)
    for field in missing:
        errors.append(f"Selection artifact is missing {field}.")
    if missing:
        return

    if selection.get("schema_version") != "TestSelectionArtifact.v1":
        errors.append("Selection artifact has invalid schema_version.")
    if selection.get("run_id") != run_artifact["run_id"]:
        errors.append("Selection artifact run_id does not match run.json.")
    if selection.get("current_commit") != run_artifact["commit_sha"]:
        errors.append("Selection artifact current_commit does not match run.json.")
    if selection.get("mode") != run_artifact["mode"]:
        errors.append("Selection artifact mode does not match run.json.")

    safety_classes = {"full_retest_all", "safe", "safe_enough", "heuristic", "advisory_only", "unknown"}
    if selection.get("selection_safety_class") not in safety_classes:
        errors.append("Selection artifact has invalid selection_safety_class.")

    changed_files = selection.get("changed_files", [])
    if not isinstance(changed_files, list):
        errors.append("Selection artifact changed_files must be a list.")
    if not isinstance(selection.get("changed_symbols", []), list):
        errors.append("Selection artifact changed_symbols must be a list.")
    if not isinstance(selection.get("candidate_tests", []), list):
        errors.append("Selection artifact candidate_tests must be a list.")
    if not isinstance(selection.get("selected_tests", []), list):
        errors.append("Selection artifact selected_tests must be a list.")

    if selection.get("mode") == "full":
        if selection.get("selection_level") != 0:
            errors.append("Full mode selection_level must be 0.")
        if selection.get("selection_safety_class") != "full_retest_all":
            errors.append("Full mode selection_safety_class must be full_retest_all.")
    if selection.get("mode") == "changed-files":
        if selection.get("selection_safety_class") not in {"safe", "safe_enough", "full_retest_all"}:
            if selection.get("full_run_required") is False and selection.get("selected_tests"):
                errors.append("Changed-files selected tests cannot be presented without full gates unless safety supports it.")
        if selection.get("selection_level", 0) >= 2 and not selection.get("candidate_tests"):
            errors.append("Selection level 2 requires candidate_tests evidence.")


def validate_run_dir(run_dir: Path) -> dict[str, object]:
    errors: list[str] = []

    required_files = [
        "run.json",
        "target_manifest.json",
        "tool_availability.json",
        "review.md",
        "findings.json",
        "centipede_bundle.json",
        "hashes.json",
    ]
    for relative in required_files:
        if not (run_dir / relative).exists():
            errors.append(f"Missing required artifact: {relative}")

    if errors:
        return {"ok": False, "errors": errors}

    run_artifact = _load_json(run_dir / "run.json")
    target_manifest = _load_json(run_dir / "target_manifest.json")
    tool_report = _load_json(run_dir / "tool_availability.json")
    findings = _load_json(run_dir / "findings.json")
    centipede_bundle = _load_json(run_dir / "centipede_bundle.json")
    hashes = _load_json(run_dir / "hashes.json")
    lanes = run_artifact.get("lanes", [])

    required_lane_artifacts: dict[str, str] = {}
    if "accuracy" in lanes:
        required_lane_artifacts["accuracy"] = "evidence/accuracy/test_evidence_bundle.json"
    if "redundancy" in lanes:
        required_lane_artifacts["redundancy"] = "evidence/redundancy/redundancy_evidence_bundle.json"
    if "efficiency" in lanes:
        required_lane_artifacts["efficiency"] = "evidence/efficiency/efficiency_evidence_bundle.json"

    evidence_bundles: dict[str, dict[str, Any]] = {}
    for lane, relative in required_lane_artifacts.items():
        path = run_dir / relative
        if not path.exists():
            errors.append(f"Missing required artifact: {relative}")
            continue
        evidence_bundles[lane] = _load_json(path)

    if errors:
        return {"ok": False, "errors": errors}

    artifacts = {
        "run.json": run_artifact,
        "target_manifest.json": target_manifest,
        "tool_availability.json": tool_report,
        "findings.json": findings,
        "centipede_bundle.json": centipede_bundle,
        **{relative: evidence_bundles[lane] for lane, relative in required_lane_artifacts.items()},
    }

    for name, payload in artifacts.items():
        if "schema_version" not in payload:
            errors.append(f"{name} is missing schema_version.")
        if payload.get("run_id") and payload["run_id"] != run_artifact["run_id"]:
            errors.append(f"{name} run_id does not match run.json.")

    selection_path = run_dir / "test_selection_artifact.json"
    if "accuracy" in lanes and run_artifact["mode"] == "changed-files" and not selection_path.exists():
        errors.append("Changed-files accuracy runs require test_selection_artifact.json.")
    if "accuracy" in lanes and run_artifact.get("test_selection_artifact_path"):
        if not selection_path.exists():
            errors.append("Referenced selection artifact is missing.")
        else:
            selection = _load_json(selection_path)
            _validate_selection_artifact(
                selection=selection,
                run_artifact=run_artifact,
                errors=errors,
            )

    if "efficiency" in lanes:
        manifest_path = run_dir / "evidence/efficiency/workload_manifest.json"
        baseline_path = run_dir / "evidence/efficiency/baseline_artifact.json"
        if not manifest_path.exists():
            errors.append("Efficiency runs require evidence/efficiency/workload_manifest.json.")
        else:
            manifest = _load_json(manifest_path)
            if "schema_version" not in manifest:
                errors.append("Efficiency workload manifest artifact is missing schema_version.")
        if not baseline_path.exists():
            errors.append("Efficiency runs require evidence/efficiency/baseline_artifact.json.")
        else:
            baseline = _load_json(baseline_path)
            if "schema_version" not in baseline:
                errors.append("Efficiency baseline artifact is missing schema_version.")
            if baseline.get("run_id") != run_artifact["run_id"]:
                errors.append("Efficiency baseline artifact run_id does not match run.json.")
            errors.extend(
                validate_eval_evidence(
                    run_dir=run_dir,
                    run_artifact=run_artifact,
                    efficiency_bundle=evidence_bundles["efficiency"],
                    baseline_artifact=baseline,
                    chain=(hashes.get("evidence_hash_chain") or {}),
                )
            )

    for field in (
        "target_manifest_path",
        "tool_availability_path",
        "review_artifact_ref",
    ):
        artifact_path = Path(run_artifact[field])
        if not artifact_path.exists():
            errors.append(f"Referenced artifact path missing: {artifact_path}")

    for path_ref in run_artifact.get("evidence_bundle_refs", []):
        if not Path(path_ref).exists():
            errors.append(f"Referenced evidence bundle missing: {path_ref}")
    for path_ref in run_artifact.get("finding_refs", []):
        if not Path(path_ref).exists():
            errors.append(f"Referenced findings file missing: {path_ref}")

    for error in validate_centipede_export_bundle(centipede_bundle):
        errors.append(error)

    for bundle in evidence_bundles.values():
        _validate_command_artifacts(bundle=bundle, errors=errors)
    _validate_finding_contracts(findings=findings, evidence_bundles=evidence_bundles, errors=errors)
    _validate_hash_chain(
        run_dir=run_dir,
        hashes=hashes,
        findings=findings,
        evidence_bundles=evidence_bundles,
        errors=errors,
    )

    hash_entries = hashes.get("entries", [])
    if not isinstance(hash_entries, list):
        errors.append("hashes.json entries must be a list.")
    else:
        for entry in hash_entries:
            target_path = run_dir / entry["path"]
            if not target_path.exists():
                errors.append(f"Hash entry path missing: {entry['path']}")
                continue
            actual_hash = sha256_path(target_path)
            if actual_hash != entry["sha256"]:
                errors.append(f"Hash mismatch for {entry['path']}")

    raw_artifact_map: dict[str, dict[str, Any]] = {}
    for bundle in evidence_bundles.values():
        for item in bundle.get("tool_raw_artifacts", []):
            raw_artifact_map[item["raw_artifact_id"]] = item

    for finding in findings.get("era_findings", []):
        refs = finding.get("raw_evidence_refs", [])
        hashes_list = finding.get("raw_evidence_hashes", [])
        if len(refs) != len(hashes_list):
            errors.append(f"Finding {finding['finding_id']} has mismatched raw evidence refs and hashes.")
            continue
        for ref, expected_hash in zip(refs, hashes_list, strict=True):
            raw = raw_artifact_map.get(ref)
            if not raw:
                errors.append(f"Finding {finding['finding_id']} references missing raw artifact {ref}.")
                continue
            if raw["sha256"] != expected_hash:
                errors.append(f"Finding {finding['finding_id']} has stale raw evidence hash for {ref}.")

    return {"ok": not errors, "errors": errors}
