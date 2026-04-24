from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from era_core.artifact_paths import resolve_era_root, utc_now_text
from era_core.hashing import sha256_json
from era_core.models import CommandResult, PlannedCommand


def detect_redundancy_commands(repo_path: Path) -> list[PlannedCommand]:
    repo_path = repo_path.resolve()
    commands: list[PlannedCommand] = []
    has_package_json = (repo_path / "package.json").exists()
    has_cargo_manifest = (repo_path / "src-tauri" / "Cargo.toml").exists() or (repo_path / "Cargo.toml").exists()
    cargo_manifest_path = "src-tauri/Cargo.toml" if (repo_path / "src-tauri" / "Cargo.toml").exists() else "Cargo.toml"

    commands.append(
        PlannedCommand(
            lane="redundancy",
            command_id="jscpd_scan",
            label="jscpd scan",
            command=["jscpd", str(repo_path), "--reporters", "console"],
            cwd=str(repo_path),
            tool_name="jscpd",
            execute=has_package_json,
            planned_status="planned" if has_package_json else "skipped",
            reason=None if has_package_json else "package.json not found.",
        )
    )
    commands.append(
        PlannedCommand(
            lane="redundancy",
            command_id="knip_scan",
            label="knip scan",
            command=["knip", "--reporter", "json"],
            cwd=str(repo_path),
            tool_name="knip",
            execute=has_package_json,
            planned_status="planned" if has_package_json else "skipped",
            reason=None if has_package_json else "package.json not found.",
            success_exit_codes=(0, 1),
        )
    )
    commands.append(
        PlannedCommand(
            lane="redundancy",
            command_id="cargo_tree_duplicates",
            label="cargo tree --duplicates",
            command=["cargo", "tree", "--duplicates", "--manifest-path", cargo_manifest_path],
            cwd=str(repo_path),
            tool_name="cargo",
            execute=has_cargo_manifest,
            planned_status="planned" if has_cargo_manifest else "skipped",
            reason=None if has_cargo_manifest else "Cargo.toml not found.",
        )
    )
    return commands


def apply_redundancy_tooling(
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
                )
            )
            continue
        planned.append(command)
    return planned


def exceptions_config_path(era_root: Path | None = None) -> Path:
    return (era_root or resolve_era_root()) / "config" / "intentional_redundancy_exceptions.json"


def load_intentional_redundancy_exceptions(
    repo_id: str,
    era_root: Path | None = None,
) -> dict[str, Any]:
    config_path = exceptions_config_path(era_root)
    if not config_path.exists():
        return {
            "schema_version": "IntentionalRedundancyExceptionSet.v1",
            "repo_id": repo_id,
            "config_path": str(config_path),
            "exceptions": [],
            "loaded_at": utc_now_text(),
        }

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        all_exceptions = payload
    else:
        all_exceptions = payload.get("exceptions", [])
    filtered = [
        item
        for item in all_exceptions
        if item.get("repo_id") in {repo_id, "*"}
    ]
    return {
        "schema_version": "IntentionalRedundancyExceptionSet.v1",
        "repo_id": repo_id,
        "config_path": str(config_path),
        "exceptions": filtered,
        "loaded_at": utc_now_text(),
    }


def _extract_path_strings(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, str):
        lowered = value.lower()
        if any(lowered.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx", ".rs", ".py", ".json", ".toml")):
            paths.append(value)
    elif isinstance(value, list):
        for item in value:
            paths.extend(_extract_path_strings(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"file", "path", "files"}:
                paths.extend(_extract_path_strings(item))
            elif isinstance(item, (dict, list)):
                paths.extend(_extract_path_strings(item))
    return paths


def _dedupe(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def _is_generated_or_fixture(paths: list[str]) -> bool:
    if not paths:
        return False
    markers = ("test", "tests", "fixture", "fixtures", "generated", "__snapshots__")
    return all(any(marker in path.lower() for marker in markers) for path in paths)


def _match_exception(
    finding: dict[str, Any],
    exceptions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    finding_paths = set(finding.get("target_files", []))
    finding_symbols = set(finding.get("target_symbols", []))
    for exception in exceptions:
        exception_paths = set(exception.get("file_paths", []))
        exception_symbols = set(exception.get("symbol_refs", []))
        if finding_paths and finding_paths.intersection(exception_paths):
            return exception
        if finding_symbols and finding_symbols.intersection(exception_symbols):
            return exception
    return None


def _build_finding(
    *,
    finding_type: str,
    summary: str,
    target_files: list[str] | None = None,
    target_symbols: list[str] | None = None,
    risk_level: str = "medium",
    confidence: str = "moderate",
    evidence_strength: str = "moderate",
) -> dict[str, Any]:
    paths = _dedupe(target_files or [])
    symbols = _dedupe(target_symbols or [])
    return {
        "finding_type": finding_type,
        "summary": summary,
        "target_files": paths,
        "target_symbols": symbols,
        "risk_level": risk_level,
        "confidence": confidence,
        "evidence_strength": evidence_strength,
        "recommended_action": "operator_review",
        "blocked_reason": None,
    }


def build_redundancy_normalized_results(
    *,
    run_id: str,
    command_results: list[CommandResult],
    raw_artifacts: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    normalizer_version: str,
) -> list[dict[str, Any]]:
    raw_refs_by_command: dict[str, list[str]] = {}
    for artifact in raw_artifacts:
        raw_refs_by_command.setdefault(artifact["command_id"], []).append(artifact["raw_artifact_id"])

    normalized_results: list[dict[str, Any]] = []
    for result in command_results:
        if result.status in {"skipped", "blocked_by_missing_tool"}:
            continue

        stdout_text = Path(result.stdout_path).read_text(encoding="utf-8") if result.stdout_path else ""
        stderr_text = Path(result.stderr_path).read_text(encoding="utf-8") if result.stderr_path else ""
        parsed_findings: list[dict[str, Any]] = []
        parse_warnings: list[str] = []

        if result.status in {"failed_to_execute", "timed_out"}:
            parse_warnings.append("Tool execution did not complete, so redundancy output could not be normalized.")
        elif result.command_id == "cargo_tree_duplicates":
            lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
            if lines:
                parsed_findings.append(
                    _build_finding(
                        finding_type="harmful_redundancy_candidate",
                        summary="cargo tree reported duplicate Rust dependencies.",
                        target_symbols=lines[:25],
                    )
                )
        elif result.command_id == "knip_scan":
            raw_payload = stdout_text.strip() or stderr_text.strip()
            try:
                payload = json.loads(raw_payload) if raw_payload else {}
            except json.JSONDecodeError:
                parse_warnings.append("Knip output was not valid JSON.")
                payload = {}

            if isinstance(payload, dict):
                for key, value in payload.items():
                    if not value:
                        continue
                    target_files = _extract_path_strings(value)
                    target_symbols: list[str] = []
                    if isinstance(value, list):
                        target_symbols = [item for item in value if isinstance(item, str)][:25]
                    elif isinstance(value, dict):
                        target_symbols = [item for item in value.keys() if isinstance(item, str)][:25]
                    parsed_findings.append(
                        _build_finding(
                            finding_type="needs_operator_review",
                            summary=f"knip reported potential redundancy/dead-code issues in `{key}`.",
                            target_files=target_files,
                            target_symbols=target_symbols,
                            risk_level="low",
                            confidence="moderate",
                            evidence_strength="moderate",
                        )
                    )
        elif result.command_id == "jscpd_scan":
            combined = "\n".join(part for part in (stdout_text, stderr_text) if part.strip())
            if re.search(r"(duplicate|duplication|clone)", combined, flags=re.IGNORECASE):
                paths = re.findall(r"[\w./-]+\.(?:ts|tsx|js|jsx|rs|py|json|toml)", combined)
                parsed_findings.append(
                    _build_finding(
                        finding_type="harmful_redundancy_candidate",
                        summary="jscpd reported duplicate code candidates.",
                        target_files=paths[:25],
                        risk_level="low",
                        confidence="low",
                        evidence_strength="low",
                    )
                )

        adjusted_findings: list[dict[str, Any]] = []
        for finding in parsed_findings:
            if _is_generated_or_fixture(finding["target_files"]):
                finding["finding_type"] = "generated_or_fixture_duplication"
                finding["risk_level"] = "low"
                finding["confidence"] = "low"
            exception = _match_exception(finding, exceptions)
            if exception is not None:
                finding["finding_type"] = "ignored_with_reason"
                finding["blocked_reason"] = exception.get("reason")
                finding["recommended_action"] = "review_exception_after_date"
                finding["exception_id"] = exception.get("exception_id")
            adjusted_findings.append(finding)

        record = {
            "schema_version": "ToolNormalizedResult.v1",
            "normalized_result_id": f"normalized:{result.command_id}",
            "run_id": run_id,
            "raw_artifact_refs": raw_refs_by_command.get(result.command_id, []),
            "normalizer_name": "era_redundancy_normalizer",
            "normalizer_version": normalizer_version,
            "tool_name": result.tool_name,
            "tool_version": result.tool_version,
            "summary_status": result.status,
            "parsed_findings": adjusted_findings,
            "parse_warnings": parse_warnings,
            "parse_errors": [],
            "created_at": result.completed_at,
        }
        record["sha256"] = sha256_json(record)
        normalized_results.append(record)
    return normalized_results
