from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from era_core.artifact_paths import resolve_era_root, utc_now_text
from era_core.contracts import build_tool_normalized_result
from era_core.hashing import sha256_json, sha256_path
from era_core.models import CommandResult, PlannedCommand

# Efficiency workloads are operator-declared commands that ERA executes verbatim.
# Restrict which executables may run to a conservative built-in set; operators can
# extend it via config/efficiency_workload_allowlist.json. Anything outside the
# effective allowlist is admitted as skipped, never executed.
DEFAULT_WORKLOAD_EXECUTABLE_ALLOWLIST = frozenset(
    {
        "git",
        "cargo",
        "bun",
        "node",
        "npm",
        "pnpm",
        "yarn",
        "python",
        "python3",
        "pytest",
        "make",
        "hyperfine",
        "jscpd",
        "knip",
        "go",
    }
)


def workload_manifests_dir(era_root: Path | None = None) -> Path:
    return (era_root or resolve_era_root()) / "config" / "workload_manifests"


def workload_allowlist_path(era_root: Path | None = None) -> Path:
    return (era_root or resolve_era_root()) / "config" / "efficiency_workload_allowlist.json"


def load_workload_executable_allowlist(era_root: Path | None = None) -> set[str]:
    """Return the effective set of executables permitted for efficiency workloads.

    The built-in conservative default is always included; an optional operator
    file extends it. The file may be either a JSON list or an object with an
    ``allowed_executables`` list.
    """
    allowed = set(DEFAULT_WORKLOAD_EXECUTABLE_ALLOWLIST)
    path = workload_allowlist_path(era_root)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        extra = payload.get("allowed_executables", []) if isinstance(payload, dict) else payload
        if isinstance(extra, list):
            allowed.update(str(item) for item in extra if isinstance(item, str) and item)
    return allowed


def _cwd_within_repo(repo_path: Path, cwd: Path) -> bool:
    if cwd == repo_path:
        return True
    return repo_path in cwd.parents


def workload_manifest_path(repo_path: Path, era_root: Path | None = None) -> Path:
    safe_name = re.sub(r"[^a-z0-9]+", "_", repo_path.name.lower()).strip("_")
    return workload_manifests_dir(era_root) / f"{safe_name}.json"


def load_efficiency_workload_manifest(
    repo_path: Path,
    repo_id: str,
    era_root: Path | None = None,
) -> dict[str, Any]:
    manifest_path = workload_manifest_path(repo_path, era_root)
    if not manifest_path.exists():
        return {
            "schema_version": "EfficiencyWorkloadManifest.v1",
            "repo_id": repo_id,
            "manifest_path": str(manifest_path),
            "manifest_status": "missing",
            "manifest_sha256": None,
            "workloads": [],
            "loaded_at": utc_now_text(),
        }

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    workloads = payload.get("workloads", []) if isinstance(payload, dict) else []
    return {
        "schema_version": payload.get("schema_version", "EfficiencyWorkloadManifest.v1"),
        "repo_id": payload.get("repo_id", repo_id),
        "manifest_path": str(manifest_path),
        "manifest_status": "loaded",
        "manifest_sha256": sha256_path(manifest_path),
        "description": payload.get("description"),
        "baseline_selection_policy": payload.get("baseline_selection_policy", "latest_prior_efficiency_run"),
        "workloads": workloads if isinstance(workloads, list) else [],
        "loaded_at": utc_now_text(),
    }


def collect_efficiency_manifest_tools(manifest: dict[str, Any]) -> list[str]:
    tools: list[str] = []
    for workload in manifest.get("workloads", []):
        command = workload.get("command", [])
        if isinstance(command, list) and command:
            tools.append(str(command[0]))
        runner = workload.get("runner", "internal_timer")
        if runner == "hyperfine":
            tools.append("hyperfine")
    return sorted({tool for tool in tools if tool})


def detect_efficiency_commands(
    repo_path: Path,
    manifest: dict[str, Any],
    allowed_executables: set[str] | None = None,
) -> list[PlannedCommand]:
    repo_path = repo_path.resolve()
    allowed = allowed_executables if allowed_executables is not None else set(
        DEFAULT_WORKLOAD_EXECUTABLE_ALLOWLIST
    )
    commands: list[PlannedCommand] = []
    for index, workload in enumerate(manifest.get("workloads", []), start=1):
        command = workload.get("command", [])
        workload_id = workload.get("workload_id") or f"workload_{index}"
        label = workload.get("label") or workload_id
        runner = workload.get("runner", "internal_timer")
        iterations = int(workload.get("iterations", 3))
        cwd_subpath = workload.get("cwd_subpath", ".")
        success_exit_codes = tuple(workload.get("success_exit_codes", [0]))
        command_is_valid = (
            isinstance(command, list) and bool(command) and all(isinstance(item, str) for item in command)
        )
        resolved_cwd = (repo_path / cwd_subpath).resolve()
        executable = command[0] if command_is_valid else None
        reason: str | None = None
        execute = True
        planned_status = "planned"

        if not command_is_valid:
            execute = False
            planned_status = "skipped"
            reason = "Workload command must be a non-empty list of strings."
        elif runner != "internal_timer":
            execute = False
            planned_status = "skipped"
            reason = f"Unsupported efficiency runner `{runner}` in ERA-01C."
        elif iterations < 2:
            execute = False
            planned_status = "skipped"
            reason = "Efficiency workloads require at least 2 iterations for variance classification."
        elif not _cwd_within_repo(repo_path, resolved_cwd):
            execute = False
            planned_status = "skipped"
            reason = f"Workload cwd_subpath `{cwd_subpath}` escapes the target repository."
        elif executable not in allowed:
            execute = False
            planned_status = "skipped"
            reason = f"Workload executable `{executable}` is not in the efficiency workload allowlist."

        command_id = f"efficiency_{re.sub(r'[^a-z0-9]+', '_', workload_id.lower()).strip('_')}"
        commands.append(
            PlannedCommand(
                lane="efficiency",
                command_id=command_id,
                label=label,
                command=command if isinstance(command, list) else [],
                cwd=str(resolved_cwd),
                tool_name=str(command[0]) if isinstance(command, list) and command else "unknown",
                execute=execute,
                planned_status=planned_status,
                reason=reason,
                success_exit_codes=success_exit_codes if success_exit_codes else (0,),
                iterations=max(1, iterations),
                lane_metadata={
                    "workload_id": workload_id,
                    "workload_label": label,
                    "workload_category": workload.get("category", "unspecified"),
                    "workload_description": workload.get("description"),
                    "workload_runner": runner,
                    "workload_executable": executable,
                    "cwd_subpath": cwd_subpath,
                    "regression_threshold_pct": float(workload.get("regression_threshold_pct", 10.0)),
                    "improvement_threshold_pct": float(workload.get("improvement_threshold_pct", 10.0)),
                    "manifest_path": manifest.get("manifest_path"),
                    "manifest_sha256": manifest.get("manifest_sha256"),
                },
            )
        )
    return commands


def apply_efficiency_tooling(
    detected_commands: list[PlannedCommand],
    tool_records: list[dict[str, object]],
) -> list[PlannedCommand]:
    tool_by_name = {item["tool"]: item for item in tool_records}
    planned: list[PlannedCommand] = []
    for command in detected_commands:
        if not command.execute:
            planned.append(command)
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
                    iterations=command.iterations,
                    lane_metadata=command.lane_metadata,
                )
            )
            continue
        planned.append(command)
    return planned


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_workload_metrics_map(command_results: list[CommandResult]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for result in command_results:
        metadata = result.lane_metadata or {}
        workload_id = metadata.get("workload_id")
        if not workload_id:
            continue
        metrics[workload_id] = {
            "command_id": result.command_id,
            "status": result.status,
            "workload_label": metadata.get("workload_label"),
            "workload_category": metadata.get("workload_category"),
            "workload_runner": metadata.get("workload_runner"),
            "timing_summary": metadata.get("timing_summary"),
            "variance_classification": metadata.get("variance_classification"),
            "regression_threshold_pct": metadata.get("regression_threshold_pct", 10.0),
            "improvement_threshold_pct": metadata.get("improvement_threshold_pct", 10.0),
        }
    return metrics


def build_efficiency_baseline_artifact(
    *,
    run_id: str,
    repo_id: str,
    current_commit_sha: str,
    branch: str,
    manifest: dict[str, Any],
    command_results: list[CommandResult],
    artifacts_root: Path,
    baseline_ref: str | None,
    baseline_commit: str | None,
) -> dict[str, Any]:
    current_metrics = _build_workload_metrics_map(command_results)
    baseline_run: dict[str, Any] | None = None
    baseline_bundle: dict[str, Any] | None = None

    candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for candidate in sorted(artifacts_root.iterdir()):
        if not candidate.is_dir() or candidate.name == run_id:
            continue
        run_path = candidate / "run.json"
        bundle_path = candidate / "evidence" / "efficiency" / "efficiency_evidence_bundle.json"
        if not run_path.exists() or not bundle_path.exists():
            continue
        run_payload = _load_json(run_path)
        if "efficiency" not in run_payload.get("lanes", []):
            continue
        if run_payload.get("repo_id") != repo_id:
            continue
        if baseline_commit and run_payload.get("commit_sha") != baseline_commit:
            continue
        if not baseline_commit and run_payload.get("branch") != branch:
            continue
        bundle_payload = _load_json(bundle_path)
        candidates.append((run_payload.get("completed_at", candidate.name), run_payload, bundle_payload))

    if candidates:
        _, baseline_run, baseline_bundle = sorted(candidates, key=lambda item: item[0])[-1]

    baseline_metrics: dict[str, Any] = {}
    if baseline_bundle is not None:
        baseline_command_results = [CommandResult(**item) for item in baseline_bundle.get("command_results", [])]
        baseline_metrics = _build_workload_metrics_map(baseline_command_results)

    comparisons: list[dict[str, Any]] = []
    for workload in manifest.get("workloads", []):
        workload_id = workload.get("workload_id")
        if not workload_id:
            continue
        current_entry = current_metrics.get(workload_id)
        baseline_entry = baseline_metrics.get(workload_id)
        comparison_status = "no_baseline"
        delta_ms = None
        delta_pct = None
        if current_entry is None or current_entry.get("status") != "passed":
            comparison_status = "workload_failed_or_unproven"
        elif baseline_entry is None or baseline_entry.get("status") != "passed":
            comparison_status = "no_baseline"
        else:
            current_variance = current_entry.get("variance_classification")
            baseline_variance = baseline_entry.get("variance_classification")
            if current_variance in {"unstable", "single_sample"} or baseline_variance in {"unstable", "single_sample"}:
                comparison_status = "unstable"
            else:
                current_median = current_entry["timing_summary"]["median_ms"]
                baseline_median = baseline_entry["timing_summary"]["median_ms"]
                delta_ms = current_median - baseline_median
                delta_pct = 0.0 if baseline_median == 0 else round((delta_ms / baseline_median) * 100.0, 3)
                regression_threshold = float(current_entry.get("regression_threshold_pct", 10.0))
                improvement_threshold = float(current_entry.get("improvement_threshold_pct", 10.0))
                if delta_pct >= regression_threshold:
                    comparison_status = "regression"
                elif delta_pct <= -improvement_threshold:
                    comparison_status = "improvement"
                else:
                    comparison_status = "within_range"

        comparisons.append(
            {
                "workload_id": workload_id,
                "workload_label": workload.get("label") or workload_id,
                "current_status": current_entry.get("status") if current_entry else "missing",
                "baseline_status": baseline_entry.get("status") if baseline_entry else "missing",
                "current_variance_classification": current_entry.get("variance_classification") if current_entry else None,
                "baseline_variance_classification": baseline_entry.get("variance_classification") if baseline_entry else None,
                "current_median_ms": (
                    (current_entry.get("timing_summary") or {}).get("median_ms") if current_entry else None
                ),
                "baseline_median_ms": (
                    (baseline_entry.get("timing_summary") or {}).get("median_ms") if baseline_entry else None
                ),
                "delta_ms": delta_ms,
                "delta_pct": delta_pct,
                "comparison_status": comparison_status,
            }
        )

    artifact = {
        "schema_version": "EfficiencyBaselineArtifact.v1",
        "run_id": run_id,
        "repo_id": repo_id,
        "current_commit_sha": current_commit_sha,
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "baseline_source_run_id": baseline_run.get("run_id") if baseline_run else None,
        "baseline_source_commit_sha": baseline_run.get("commit_sha") if baseline_run else None,
        "baseline_source_branch": baseline_run.get("branch") if baseline_run else None,
        "baseline_found": baseline_run is not None,
        "baseline_selection_policy": manifest.get("baseline_selection_policy", "latest_prior_efficiency_run"),
        "comparisons": comparisons,
        "created_at": utc_now_text(),
    }
    artifact["sha256"] = sha256_json(artifact)
    return artifact


def build_efficiency_normalized_results(
    *,
    run_id: str,
    command_results: list[CommandResult],
    raw_artifacts: list[dict[str, Any]],
    baseline_artifact: dict[str, Any],
    normalizer_version: str,
) -> list[dict[str, Any]]:
    raw_refs_by_command: dict[str, list[str]] = {}
    for artifact in raw_artifacts:
        raw_refs_by_command.setdefault(artifact["command_id"], []).append(artifact["raw_artifact_id"])
    comparisons_by_workload = {
        item["workload_id"]: item for item in baseline_artifact.get("comparisons", [])
    }

    normalized_results: list[dict[str, Any]] = []
    for result in command_results:
        if result.status in {"skipped", "blocked_by_missing_tool"}:
            continue
        metadata = result.lane_metadata or {}
        workload_id = metadata.get("workload_id")
        comparison = comparisons_by_workload.get(workload_id, {})
        parsed_findings: list[dict[str, Any]] = []
        parse_warnings: list[str] = []

        if result.status in {"failed_to_execute", "timed_out"}:
            parse_warnings.append("Efficiency workload did not complete, so no timing claim could be made.")
        else:
            status = comparison.get("comparison_status")
            if status == "no_baseline":
                parse_warnings.append("No baseline artifact was available, so no regression or improvement claim was made.")
            elif status == "unstable":
                parse_warnings.append("Workload timing variance was too unstable for a mechanical claim.")
            elif status == "regression":
                delta_pct = comparison.get("delta_pct") or 0.0
                parsed_findings.append(
                    {
                        "finding_type": "efficiency_regression_with_baseline",
                        "summary": "Efficiency workload regressed relative to the selected baseline.",
                        "target_files": [],
                        "target_symbols": [metadata.get("workload_label") or workload_id],
                        "risk_level": "high" if delta_pct >= 25.0 else "medium",
                        "confidence": "high",
                        "evidence_strength": "high",
                        "recommended_action": "operator_review",
                        "blocked_reason": None,
                        "lane_details": {
                            "workload_id": workload_id,
                            "workload_label": metadata.get("workload_label"),
                            "comparison_status": status,
                            "delta_pct": delta_pct,
                            "variance_classification": metadata.get("variance_classification"),
                            "timing_summary": metadata.get("timing_summary"),
                        },
                    }
                )

        normalized_results.append(
            build_tool_normalized_result(
                run_id=run_id,
                command_id=result.command_id,
                raw_artifact_refs=raw_refs_by_command.get(result.command_id, []),
                normalizer_name="era_efficiency_normalizer",
                normalizer_version=normalizer_version,
                tool_name=result.tool_name,
                tool_version=result.tool_version,
                summary_status=result.status,
                parsed_findings=parsed_findings,
                parse_warnings=parse_warnings,
                parse_errors=[],
                created_at=result.completed_at,
            )
        )
    return normalized_results
