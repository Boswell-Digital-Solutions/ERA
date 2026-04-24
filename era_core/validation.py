from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.hashing import sha256_path


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


def validate_run_dir(run_dir: Path) -> dict[str, object]:
    errors: list[str] = []

    required_files = [
        "run.json",
        "target_manifest.json",
        "tool_availability.json",
        "review.md",
        "findings.json",
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
    hashes = _load_json(run_dir / "hashes.json")
    lanes = run_artifact.get("lanes", [])

    required_lane_artifacts: dict[str, str] = {}
    if "accuracy" in lanes:
        required_lane_artifacts["accuracy"] = "evidence/accuracy/test_evidence_bundle.json"
    if "redundancy" in lanes:
        required_lane_artifacts["redundancy"] = "evidence/redundancy/redundancy_evidence_bundle.json"

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
        **{relative: evidence_bundles[lane] for lane, relative in required_lane_artifacts.items()},
    }

    for name, payload in artifacts.items():
        if "schema_version" not in payload:
            errors.append(f"{name} is missing schema_version.")
        if payload.get("run_id") and payload["run_id"] != run_artifact["run_id"]:
            errors.append(f"{name} run_id does not match run.json.")

    if "accuracy" in lanes and run_artifact["mode"] == "changed-files":
        selection_path = run_dir / "test_selection_artifact.json"
        if not selection_path.exists():
            errors.append("Changed-files accuracy runs require test_selection_artifact.json.")
        else:
            selection = _load_json(selection_path)
            if selection.get("run_id") != run_artifact["run_id"]:
                errors.append("Selection artifact run_id does not match run.json.")
            if "schema_version" not in selection:
                errors.append("Selection artifact is missing schema_version.")

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

    for bundle in evidence_bundles.values():
        _validate_command_artifacts(bundle=bundle, errors=errors)

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
