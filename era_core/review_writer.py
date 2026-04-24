from __future__ import annotations

from pathlib import Path
from typing import Any

from era_core.models import CommandResult


def determine_accuracy_classification(
    command_results: list[CommandResult],
    read_only_invariant_status: str,
) -> str:
    if read_only_invariant_status in {"read_only_invariant_failed", "head_changed_during_run"}:
        return "blocked_by_missing_evidence"
    if any(item.status in {"failed_to_execute", "timed_out"} for item in command_results):
        return "blocked_by_missing_evidence"
    if any(item.status == "failed" for item in command_results):
        return "inaccurate"
    if any(item.status == "blocked_by_missing_tool" for item in command_results):
        return "blocked_by_missing_evidence"
    if not any(item.status not in {"skipped", "blocked_by_missing_tool"} for item in command_results):
        return "unproven"
    return "accurate_enough_for_review"


def determine_redundancy_classification(
    command_results: list[CommandResult],
    findings: list[dict[str, Any]],
) -> str:
    executed = [item for item in command_results if item.status not in {"skipped", "blocked_by_missing_tool"}]
    if not executed and any(item.status == "blocked_by_missing_tool" for item in command_results):
        return "blocked_by_missing_tool"
    if any(item.status in {"failed_to_execute", "timed_out"} for item in command_results):
        return "blocked_by_missing_evidence"
    if findings:
        return "needs_operator_review"
    if not executed:
        return "unproven"
    return "no_mechanical_redundancy_candidates"


def _fmt_path(path_value: str | None) -> str:
    return path_value or "n/a"


def _append_command_summary(lines: list[str], command_results: list[CommandResult]) -> None:
    lines.extend(
        [
            "| label | status | exit code | duration ms | stdout | stderr |",
            "|---|---|---:|---:|---|---|",
        ]
    )
    for result in command_results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.label,
                    result.status,
                    str(result.exit_code) if result.exit_code is not None else "n/a",
                    str(result.duration_ms),
                    _fmt_path(result.stdout_path),
                    _fmt_path(result.stderr_path),
                ]
            )
            + " |"
        )


def write_review(
    *,
    run_artifact: dict[str, object],
    tool_report: dict[str, object],
    selection_artifact: dict[str, object] | None,
    evidence_bundles: dict[str, dict[str, object]],
    findings_bundle: dict[str, object],
    lane_classifications: dict[str, str],
    exceptions_bundle: dict[str, object] | None,
    output_path: Path,
) -> None:
    lines: list[str] = [
        "# ERA Review",
        "",
        f"Run ID: `{run_artifact['run_id']}`",
        f"Target Repo: `{run_artifact['repo_path']}`",
        f"Commit SHA: `{run_artifact['commit_sha']}`",
        f"Branch: `{run_artifact['branch']}`",
        f"Lanes: `{', '.join(run_artifact['lanes'])}`",
        f"Working Tree Dirty Status: `{run_artifact['is_dirty']}`",
        f"Started / Completed: `{run_artifact['started_at']}` / `{run_artifact['completed_at']}`",
        f"Overall Status: `{run_artifact['status']}`",
        "",
        "## Tool Availability",
        "| tool | status | version | note |",
        "|---|---|---|---|",
    ]
    for tool in tool_report["tools"]:
        lines.append(
            f"| {tool['tool']} | {tool['status']} | {tool['version'] or 'n/a'} | {tool['note'] or 'n/a'} |"
        )

    if "accuracy" in run_artifact["lanes"]:
        command_results = [CommandResult(**item) for item in evidence_bundles["accuracy"]["command_results"]]
        failed = [item for item in command_results if item.status in {"failed", "timed_out", "failed_to_execute"}]
        skipped_or_blocked = [item for item in command_results if item.status in {"skipped", "blocked_by_missing_tool"}]
        lines.extend(
            [
                "",
                "## Accuracy Lane",
                f"Classification: `{lane_classifications['accuracy']}`",
                "",
                "### Delta / RTS Summary",
                f"- baseline: `{(selection_artifact or {}).get('baseline_ref') or 'n/a'}`",
                f"- changed files: `{len((selection_artifact or {}).get('changed_files', []))}`",
                f"- selected tests: `{', '.join((selection_artifact or {}).get('selected_tests', [])) or 'none'}`",
                f"- full gates run or not: `{(selection_artifact or {}).get('full_run_executed', False)}`",
                f"- selection method: `{(selection_artifact or {}).get('selection_method', 'n/a')}`",
                f"- confidence classification: `{(selection_artifact or {}).get('selection_safety_class', 'n/a')}`",
                f"- fallback reason: `{(selection_artifact or {}).get('fallback_reason') or 'n/a'}`",
                "",
                "### Command Summary",
            ]
        )
        _append_command_summary(lines, command_results)
        lines.extend(["", "### Failed Commands"])
        if failed:
            for item in failed:
                lines.append(
                    f"- `{item.label}` status=`{item.status}` exit_code=`{item.exit_code}` stdout=`{_fmt_path(item.stdout_path)}` stderr=`{_fmt_path(item.stderr_path)}`"
                )
        else:
            lines.append("- none")
        lines.extend(["", "### Skipped / Blocked Commands"])
        if skipped_or_blocked:
            for item in skipped_or_blocked:
                lines.append(
                    f"- `{item.label}` status=`{item.status}` reason=`{item.blocked_reason or 'n/a'}`"
                )
        else:
            lines.append("- none")

    if "redundancy" in run_artifact["lanes"]:
        command_results = [CommandResult(**item) for item in evidence_bundles["redundancy"]["command_results"]]
        skipped_or_blocked = [item for item in command_results if item.status in {"skipped", "blocked_by_missing_tool"}]
        redundancy_findings = [
            item for item in findings_bundle["era_findings"] if item["lane"] == "redundancy"
        ]
        lines.extend(
            [
                "",
                "## Redundancy Lane",
                f"Classification: `{lane_classifications['redundancy']}`",
                "",
                "### Exception Model",
                f"- config path: `{(exceptions_bundle or {}).get('config_path', 'n/a')}`",
                f"- loaded exceptions: `{len((exceptions_bundle or {}).get('exceptions', []))}`",
                "",
                "### Command Summary",
            ]
        )
        _append_command_summary(lines, command_results)
        lines.extend(["", "### Candidate Findings"])
        if redundancy_findings:
            for finding in redundancy_findings:
                lines.append(
                    f"- `{finding['finding_type']}` risk=`{finding['risk_level']}` confidence=`{finding['confidence']}` files=`{', '.join(finding['target_files']) or 'n/a'}` reason=`{finding.get('blocked_reason') or 'n/a'}`"
                )
        else:
            lines.append("- none")
        lines.extend(["", "### Skipped / Blocked Commands"])
        if skipped_or_blocked:
            for item in skipped_or_blocked:
                lines.append(
                    f"- `{item.label}` status=`{item.status}` reason=`{item.blocked_reason or 'n/a'}`"
                )
        else:
            lines.append("- none")

    lines.extend(
        [
            "",
            "## Read-Only Invariant",
            f"- status: `{run_artifact['read_only_invariant_status']}`",
            f"- before: `{run_artifact['pre_run_git_status_short'] or 'clean'}`",
            f"- after: `{run_artifact['post_run_git_status_short'] or 'clean'}`",
            f"- notes: `{run_artifact['read_only_invariant_notes']}`",
            "",
            "## Operator Notes",
            "- No automatic action was taken.",
            "- ERA is read-only.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
