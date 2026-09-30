from __future__ import annotations

from pathlib import Path
from typing import Any

from era_core.eval_review import load_eval_artifacts, render_eval_section
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


def determine_efficiency_classification(
    command_results: list[CommandResult],
    baseline_artifact: dict[str, Any],
    findings: list[dict[str, Any]],
) -> str:
    executed = [item for item in command_results if item.status not in {"skipped", "blocked_by_missing_tool"}]
    if not executed and any(item.status == "blocked_by_missing_tool" for item in command_results):
        return "blocked_by_missing_tool"
    if any(item.status in {"failed_to_execute", "timed_out"} for item in command_results):
        return "blocked_by_missing_evidence"
    if not executed:
        return "unproven"
    comparisons = baseline_artifact.get("comparisons", [])
    # A quality failure controls the outcome. Timing cannot outweigh it.
    if any(item.get("comparison_status") == "quality_blocked" for item in comparisons):
        return "quality_blocked"
    if any(item.get("comparison_status") == "evidence_blocked" for item in comparisons):
        return "blocked_by_missing_evidence"
    if any(item.get("comparison_status") == "quality_unproven" for item in comparisons):
        return "quality_unproven"
    if any(item.get("comparison_status") == "incomparable" for item in comparisons):
        return "incomparable"
    if any(item["finding_type"] == "efficiency_regression_with_baseline" for item in findings):
        return "regression_with_baseline"

    if any(item.get("comparison_status") == "unstable" for item in comparisons):
        return "unstable"
    if not any(item.get("comparison_status") in {"within_range", "improvement", "regression"} for item in comparisons):
        return "unproven"
    return "within_expected_range"


def _workload_status_text(comparison: dict[str, Any]) -> str:
    """Status text for the workload table. A gated workload always shows its gates."""
    status = str(comparison.get("comparison_status", "n/a"))
    if comparison.get("evaluation"):
        return f"{status} (claim {comparison.get('claim_status', 'n/a')}, quality {comparison.get('quality_status', 'n/a')})"
    return status


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
    efficiency_manifest: dict[str, object] | None,
    efficiency_baseline_artifact: dict[str, object] | None,
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
    score_rows = findings_bundle.get("era_scores", [])
    if score_rows:
        lines.extend(
            [
                "",
                "## Score Summary",
                "| scope | classification | commands | drafts | findings |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for score in score_rows:
            scope = score["scope"] if score["scope"] == "overall" else str(score.get("lane") or score["scope"])
            lines.append(
                "| "
                + " | ".join(
                    [
                        scope,
                        str(score.get("classification", "n/a")),
                        str(score.get("command_count", 0)),
                        str(score.get("draft_count", 0)),
                        str(score.get("finding_count", 0)),
                    ]
                )
                + " |"
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
                f"- current commit: `{(selection_artifact or {}).get('current_commit') or run_artifact['commit_sha']}`",
                f"- changed files: `{len((selection_artifact or {}).get('changed_files', []))}`",
                f"- changed file classes: `{', '.join((selection_artifact or {}).get('changed_file_classification', {}).keys()) or 'none'}`",
                f"- selected tests: `{', '.join((selection_artifact or {}).get('selected_tests', [])) or 'none'}`",
                f"- full gates run or not: `{(selection_artifact or {}).get('full_run_executed', False)}`",
                f"- RTS level cap: `{(selection_artifact or {}).get('rts_level_cap', 'n/a')}`",
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
                    f"- `{finding['finding_type']}` risk=`{finding['risk_level']}` confidence=`{finding['confidence']}` summary=`{finding.get('summary') or 'n/a'}` files=`{', '.join(finding['target_files']) or 'n/a'}` reason=`{finding.get('blocked_reason') or 'n/a'}`"
                )
        else:
            lines.append("- none")

    if "efficiency" in run_artifact["lanes"]:
        command_results = [CommandResult(**item) for item in evidence_bundles["efficiency"]["command_results"]]
        skipped_or_blocked = [item for item in command_results if item.status in {"skipped", "blocked_by_missing_tool"}]
        efficiency_findings = [
            item for item in findings_bundle["era_findings"] if item["lane"] == "efficiency"
        ]
        comparisons = (efficiency_baseline_artifact or {}).get("comparisons", [])
        lines.extend(
            [
                "",
                "## Efficiency Lane",
                f"Classification: `{lane_classifications['efficiency']}`",
                "",
                "### Workload Manifest",
                f"- manifest path: `{(efficiency_manifest or {}).get('manifest_path', 'n/a')}`",
                f"- manifest status: `{(efficiency_manifest or {}).get('manifest_status', 'n/a')}`",
                f"- workloads declared: `{len((efficiency_manifest or {}).get('workloads', []))}`",
                "",
                "### Baseline Summary",
                f"- baseline found: `{(efficiency_baseline_artifact or {}).get('baseline_found', False)}`",
                f"- baseline source run: `{(efficiency_baseline_artifact or {}).get('baseline_source_run_id') or 'n/a'}`",
                f"- baseline source commit: `{(efficiency_baseline_artifact or {}).get('baseline_source_commit_sha') or 'n/a'}`",
                "",
                "### Workload Summary",
                "| workload | status | iterations | median ms | variance | baseline status | delta % |",
                "|---|---|---:|---:|---|---|---:|",
            ]
        )
        comparison_by_workload = {item["workload_id"]: item for item in comparisons}
        eval_refs = evidence_bundles["efficiency"].get("evaluation_evidence_refs") or {}
        eval_artifacts = load_eval_artifacts(Path(str(run_artifact["artifact_root"])), eval_refs)
        for result in command_results:
            metadata = result.lane_metadata or {}
            workload_id = metadata.get("workload_id", result.command_id)
            timing_summary = metadata.get("timing_summary") or {}
            comparison = comparison_by_workload.get(workload_id, {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(metadata.get("workload_label") or workload_id),
                        result.status,
                        str(metadata.get("iterations_completed", 0)),
                        str(timing_summary.get("median_ms", "n/a")),
                        str(metadata.get("variance_classification", "n/a")),
                        _workload_status_text(comparison),
                        str(comparison.get("delta_pct", "n/a")),
                    ]
                )
                + " |"
            )
        if not command_results:
            lines.append("| none | n/a | 0 | n/a | n/a | n/a | n/a |")

        lines.extend(render_eval_section(eval_refs, eval_artifacts))

        lines.extend(["", "### Candidate Findings"])
        if efficiency_findings:
            for finding in efficiency_findings:
                lines.append(
                    f"- `{finding['finding_type']}` risk=`{finding['risk_level']}` confidence=`{finding['confidence']}` summary=`{finding.get('summary') or 'n/a'}` symbols=`{', '.join(finding['target_symbols']) or 'n/a'}`"
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
            "## Hash References",
            f"- findings bundle: `{findings_bundle.get('sha256', 'n/a')}`",
            "",
            "### Evidence Bundles",
            "| lane | hash |",
            "|---|---|",
        ]
    )
    for lane, bundle in sorted(evidence_bundles.items()):
        lines.append(f"| {lane} | {bundle.get('sha256', 'n/a')} |")
    lines.extend(
        [
            "",
            "### Finding Hashes",
            "| finding | lane | hash |",
            "|---|---|---|",
        ]
    )
    for finding in findings_bundle.get("era_findings", []):
        lines.append(f"| {finding['finding_id']} | {finding['lane']} | {finding.get('sha256', 'n/a')} |")
    if not findings_bundle.get("era_findings", []):
        lines.append("| none | n/a | n/a |")
    lines.extend(
        [
            "",
            "### Score Hashes",
            "| score | scope | hash |",
            "|---|---|---|",
        ]
    )
    for score in findings_bundle.get("era_scores", []):
        scope = score["scope"] if score["scope"] == "overall" else str(score.get("lane") or score["scope"])
        lines.append(f"| {score['score_id']} | {scope} | {score.get('sha256', 'n/a')} |")
    if not findings_bundle.get("era_scores", []):
        lines.append("| none | n/a | n/a |")

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
