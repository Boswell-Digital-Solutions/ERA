from __future__ import annotations

import json
from pathlib import Path

from era_core.artifact_paths import utc_now_text
from era_core.models import PlannedCommand


def _load_package_scripts(repo_path: Path) -> dict[str, str]:
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return {}
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    scripts = payload.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


def detect_accuracy_commands(repo_path: Path) -> list[PlannedCommand]:
    repo_path = repo_path.resolve()
    commands: list[PlannedCommand] = []
    cargo_manifest = repo_path / "src-tauri" / "Cargo.toml"
    cargo_reason = None if cargo_manifest.exists() else "src-tauri/Cargo.toml not found."
    commands.append(
        PlannedCommand(
            lane="accuracy",
            command_id="cargo_check",
            label="cargo check",
            command=["cargo", "check", "--manifest-path", "src-tauri/Cargo.toml"],
            cwd=str(repo_path),
            tool_name="cargo",
            execute=cargo_manifest.exists(),
            planned_status="planned" if cargo_manifest.exists() else "skipped",
            reason=cargo_reason,
        )
    )
    commands.append(
        PlannedCommand(
            lane="accuracy",
            command_id="cargo_test",
            label="cargo test",
            command=["cargo", "test", "--manifest-path", "src-tauri/Cargo.toml"],
            cwd=str(repo_path),
            tool_name="cargo",
            execute=cargo_manifest.exists(),
            planned_status="planned" if cargo_manifest.exists() else "skipped",
            reason=cargo_reason,
        )
    )

    scripts = _load_package_scripts(repo_path)
    package_exists = (repo_path / "package.json").exists()
    bun_test_reason = None
    bun_build_reason = None
    bun_test_enabled = False
    bun_build_enabled = False
    if not package_exists:
        bun_test_reason = "package.json not found."
        bun_build_reason = "package.json not found."
    else:
        bun_test_enabled = "test" in scripts
        bun_build_enabled = "build" in scripts
        if not bun_test_enabled:
            bun_test_reason = "package.json has no test script."
        if not bun_build_enabled:
            bun_build_reason = "package.json has no build script."

    commands.append(
        PlannedCommand(
            lane="accuracy",
            command_id="bun_test",
            label="bun test",
            command=["bun", "test"],
            cwd=str(repo_path),
            tool_name="bun",
            execute=bun_test_enabled,
            planned_status="planned" if bun_test_enabled else "skipped",
            reason=bun_test_reason,
        )
    )
    commands.append(
        PlannedCommand(
            lane="accuracy",
            command_id="bun_build",
            label="bun run build",
            command=["bun", "run", "build"],
            cwd=str(repo_path),
            tool_name="bun",
            execute=bun_build_enabled,
            planned_status="planned" if bun_build_enabled else "skipped",
            reason=bun_build_reason,
        )
    )
    return commands


def _candidate_tests(changed_files: list[str]) -> list[str]:
    candidates = []
    for path in changed_files:
        lowered = path.lower()
        if "/tests/" in f"/{lowered}" or ".test." in lowered or ".spec." in lowered:
            candidates.append(path)
    return candidates


def build_selection_artifact(
    *,
    run_id: str,
    repo_id: str,
    baseline_ref: str | None,
    baseline_commit: str | None,
    current_commit: str,
    mode: str,
    changed_files: list[str],
) -> dict[str, object]:
    candidate_tests = _candidate_tests(changed_files)
    if mode == "full":
        return {
            "schema_version": "TestSelectionArtifact.v1",
            "run_id": run_id,
            "repo_id": repo_id,
            "baseline_ref": baseline_ref,
            "baseline_commit": baseline_commit,
            "current_commit": current_commit,
            "mode": mode,
            "selection_level": 0,
            "selection_method": "full_retest_all",
            "selection_safety_class": "full_retest_all",
            "changed_files": changed_files,
            "changed_symbols": [],
            "candidate_tests": candidate_tests,
            "selected_tests": [],
            "excluded_tests": [],
            "full_run_required": True,
            "full_run_executed": True,
            "fallback_reason": None,
            "coverage_snapshot_ref": None,
            "manifest_mapping_ref": None,
            "rts_tool_name": None,
            "rts_tool_version": None,
            "selection_rationale": "Full mode always runs all configured accuracy gates.",
            "created_at": utc_now_text(),
        }

    if not baseline_ref:
        return {
            "schema_version": "TestSelectionArtifact.v1",
            "run_id": run_id,
            "repo_id": repo_id,
            "baseline_ref": baseline_ref,
            "baseline_commit": baseline_commit,
            "current_commit": current_commit,
            "mode": mode,
            "selection_level": 1,
            "selection_method": "changed_file_metadata_full_fallback",
            "selection_safety_class": "unknown",
            "changed_files": changed_files,
            "changed_symbols": [],
            "candidate_tests": candidate_tests,
            "selected_tests": [],
            "excluded_tests": [],
            "full_run_required": True,
            "full_run_executed": False,
            "fallback_reason": "No baseline ref was provided for changed-files mode.",
            "coverage_snapshot_ref": None,
            "manifest_mapping_ref": None,
            "rts_tool_name": None,
            "rts_tool_version": None,
            "selection_rationale": "Changed-file metadata was incomplete, so ERA fell back to full gates.",
            "created_at": utc_now_text(),
        }

    if not baseline_commit:
        return {
            "schema_version": "TestSelectionArtifact.v1",
            "run_id": run_id,
            "repo_id": repo_id,
            "baseline_ref": baseline_ref,
            "baseline_commit": baseline_commit,
            "current_commit": current_commit,
            "mode": mode,
            "selection_level": 1,
            "selection_method": "changed_file_metadata_full_fallback",
            "selection_safety_class": "unknown",
            "changed_files": changed_files,
            "changed_symbols": [],
            "candidate_tests": candidate_tests,
            "selected_tests": [],
            "excluded_tests": [],
            "full_run_required": True,
            "full_run_executed": False,
            "fallback_reason": f"Unable to resolve baseline ref `{baseline_ref}`.",
            "coverage_snapshot_ref": None,
            "manifest_mapping_ref": None,
            "rts_tool_name": None,
            "rts_tool_version": None,
            "selection_rationale": "Changed-file metadata was incomplete, so ERA fell back to full gates.",
            "created_at": utc_now_text(),
        }

    if not changed_files:
        return {
            "schema_version": "TestSelectionArtifact.v1",
            "run_id": run_id,
            "repo_id": repo_id,
            "baseline_ref": baseline_ref,
            "baseline_commit": baseline_commit,
            "current_commit": current_commit,
            "mode": mode,
            "selection_level": 1,
            "selection_method": "changed_file_metadata_no_changes",
            "selection_safety_class": "advisory_only",
            "changed_files": [],
            "changed_symbols": [],
            "candidate_tests": [],
            "selected_tests": [],
            "excluded_tests": [],
            "full_run_required": False,
            "full_run_executed": False,
            "fallback_reason": "No changed files were detected relative to the baseline and working tree.",
            "coverage_snapshot_ref": None,
            "manifest_mapping_ref": None,
            "rts_tool_name": None,
            "rts_tool_version": None,
            "selection_rationale": "ERA recorded changed-file metadata only; no safe selective execution was inferred.",
            "created_at": utc_now_text(),
        }

    return {
        "schema_version": "TestSelectionArtifact.v1",
        "run_id": run_id,
        "repo_id": repo_id,
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "current_commit": current_commit,
        "mode": mode,
        "selection_level": 1,
        "selection_method": "changed_file_metadata_full_fallback",
        "selection_safety_class": "heuristic",
        "changed_files": changed_files,
        "changed_symbols": [],
        "candidate_tests": candidate_tests,
        "selected_tests": [],
        "excluded_tests": [],
        "full_run_required": True,
        "full_run_executed": False,
        "fallback_reason": "ERA-01A does not yet map changed files to a safe subset of accuracy gates.",
        "coverage_snapshot_ref": None,
        "manifest_mapping_ref": None,
        "rts_tool_name": None,
        "rts_tool_version": None,
        "selection_rationale": "Changed-file metadata was captured, then ERA fell back to full configured gates.",
        "created_at": utc_now_text(),
    }


def apply_selection_and_tooling(
    detected_commands: list[PlannedCommand],
    tool_records: list[dict[str, object]],
    selection_artifact: dict[str, object],
) -> list[PlannedCommand]:
    tool_by_name = {item["tool"]: item for item in tool_records}
    hold_execution = (
        selection_artifact["mode"] == "changed-files"
        and not selection_artifact["full_run_required"]
    )

    planned: list[PlannedCommand] = []
    for command in detected_commands:
        if not command.execute:
            planned.append(command)
            continue
        if hold_execution:
            planned.append(
                PlannedCommand(
                    lane=command.lane,
                    command_id=command.command_id,
                    label=command.label,
                    command=command.command,
                    cwd=command.cwd,
                    tool_name=command.tool_name,
                    execute=False,
                    planned_status="skipped",
                    reason=str(selection_artifact["fallback_reason"]),
                    success_exit_codes=command.success_exit_codes,
                )
            )
            continue
        tool = tool_by_name.get(command.tool_name)
        if tool and tool["status"] != "available":
            status = "blocked_by_missing_tool" if tool["status"] == "missing" else "skipped"
            planned.append(
                PlannedCommand(
                    lane=command.lane,
                    command_id=command.command_id,
                    label=command.label,
                    command=command.command,
                    cwd=command.cwd,
                    tool_name=command.tool_name,
                    execute=False,
                    planned_status=status,
                    reason=f"{command.tool_name} status is {tool['status']}.",
                    success_exit_codes=command.success_exit_codes,
                )
            )
            continue
        planned.append(command)
    return planned
