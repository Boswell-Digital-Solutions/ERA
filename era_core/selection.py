from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
            label="bun run test",
            # Invoke the project's declared `test` script (`bun run test`) rather
            # than Bun's native `bun test` runner. A bare `bun test` only suits
            # repos with native `bun:test` specs; for Vitest/Jest projects it runs
            # the wrong runner and produces spurious accuracy-gate failures. The
            # `bun_test_enabled` guard above already requires a declared `test`
            # script, so `bun run test` always has a target to dispatch.
            command=["bun", "run", "test"],
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
    return sorted(candidates)


def _classify_changed_file(path: str) -> str:
    lowered = path.lower()
    name = Path(path).name.lower()
    if lowered.startswith("docs/") or name.endswith((".md", ".rst", ".txt")):
        return "documentation"
    if any(marker in lowered for marker in ("/generated/", "/__generated__/", ".generated.")):
        return "generated"
    if name in {"package.json", "cargo.toml", "pyproject.toml", "tsconfig.json"}:
        return "configuration"
    if name.endswith(("lock", ".lock")) or name in {"cargo.lock", "bun.lock", "package-lock.json"}:
        return "lockfile"
    if "/tests/" in f"/{lowered}" or ".test." in lowered or ".spec." in lowered:
        return "test"
    if name.endswith((".rs", ".ts", ".tsx", ".js", ".jsx", ".py")):
        return "source"
    return "unknown"


def _changed_file_classification(changed_files: list[str]) -> dict[str, list[str]]:
    classified: dict[str, list[str]] = {}
    for path in changed_files:
        classified.setdefault(_classify_changed_file(path), []).append(path)
    return {key: sorted(values) for key, values in sorted(classified.items())}


def _selection_base(
    *,
    run_id: str,
    repo_id: str,
    baseline_ref: str | None,
    baseline_commit: str | None,
    current_commit: str,
    mode: str,
    changed_files: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "TestSelectionArtifact.v1",
        "run_id": run_id,
        "repo_id": repo_id,
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "current_commit": current_commit,
        "mode": mode,
        "changed_files": changed_files,
        "changed_symbols": [],
        "changed_file_classification": _changed_file_classification(changed_files),
        "candidate_tests": _candidate_tests(changed_files),
        "selected_tests": [],
        "excluded_tests": [],
        "coverage_snapshot_ref": None,
        "manifest_mapping_ref": None,
        "rts_tool_name": None,
        "rts_tool_version": None,
        "created_at": utc_now_text(),
    }


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
    artifact = _selection_base(
        run_id=run_id,
        repo_id=repo_id,
        baseline_ref=baseline_ref,
        baseline_commit=baseline_commit,
        current_commit=current_commit,
        mode=mode,
        changed_files=changed_files,
    )
    if mode == "full":
        artifact.update(
            {
                "selection_level": 0,
                "selection_method": "full_retest_all",
                "selection_safety_class": "full_retest_all",
                "rts_level_cap": 0,
                "full_run_required": True,
                "full_run_executed": True,
                "fallback_reason": None,
                "selection_rationale": "Full mode always runs all configured accuracy gates.",
            }
        )
        return artifact

    if not baseline_ref:
        artifact.update(
            {
                "selection_level": 1,
                "selection_method": "changed_file_metadata_full_fallback",
                "selection_safety_class": "unknown",
                "rts_level_cap": 1,
                "full_run_required": True,
                "full_run_executed": False,
                "fallback_reason": "No baseline ref was provided for changed-files mode.",
                "selection_rationale": "Changed-file metadata was incomplete, so ERA fell back to full gates.",
            }
        )
        return artifact

    if not baseline_commit:
        artifact.update(
            {
                "selection_level": 1,
                "selection_method": "changed_file_metadata_full_fallback",
                "selection_safety_class": "unknown",
                "rts_level_cap": 1,
                "full_run_required": True,
                "full_run_executed": False,
                "fallback_reason": f"Unable to resolve baseline ref `{baseline_ref}`.",
                "selection_rationale": "Changed-file metadata was incomplete, so ERA fell back to full gates.",
            }
        )
        return artifact

    if not changed_files:
        artifact.update(
            {
                "selection_level": 1,
                "selection_method": "changed_file_metadata_no_changes",
                "selection_safety_class": "advisory_only",
                "rts_level_cap": 1,
                "full_run_required": False,
                "full_run_executed": False,
                "fallback_reason": "No changed files were detected relative to the baseline and working tree.",
                "selection_rationale": "ERA recorded changed-file metadata only; no safe selective execution was inferred.",
            }
        )
        return artifact

    classification = artifact["changed_file_classification"]
    changed_kinds = set(classification)
    candidate_tests = artifact["candidate_tests"]
    only_test_files = bool(candidate_tests) and changed_kinds.issubset({"test", "documentation"})
    if only_test_files:
        artifact.update(
            {
                "selection_level": 2,
                "selection_method": "changed_test_file_advisory_full_fallback",
                "selection_safety_class": "heuristic",
                "rts_level_cap": 2,
                "selected_tests": candidate_tests,
                "full_run_required": True,
                "full_run_executed": False,
                "fallback_reason": "Direct test-file selection was obvious, but ERA-04 still requires full gates until targeted execution is implemented.",
                "selection_rationale": "ERA recorded the directly changed test files as advisory selected tests, then fell back to full configured accuracy gates.",
            }
        )
        return artifact

    artifact.update(
        {
            "selection_level": 1,
            "selection_method": "changed_file_metadata_full_fallback",
            "selection_safety_class": "heuristic",
            "rts_level_cap": 1,
            "full_run_required": True,
            "full_run_executed": False,
            "fallback_reason": "ERA-04 does not yet map changed files to a safe subset of accuracy gates.",
            "selection_rationale": "Changed-file metadata was captured, then ERA fell back to full configured gates.",
        }
    )
    return artifact


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
