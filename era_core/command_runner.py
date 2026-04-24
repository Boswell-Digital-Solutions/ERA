from __future__ import annotations

import subprocess
import time
from pathlib import Path

from era_core.artifact_paths import utc_now_text
from era_core.hashing import sha256_bytes
from era_core.models import CommandResult, PlannedCommand


def _write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def run_planned_commands(
    planned_commands: list[PlannedCommand],
    commands_dirs: dict[str, Path],
    tool_versions: dict[str, str],
    timeout_seconds: int = 1800,
) -> list[CommandResult]:
    results: list[CommandResult] = []
    for planned in planned_commands:
        started_at = utc_now_text()
        if not planned.execute:
            results.append(
                CommandResult(
                    lane=planned.lane,
                    command_id=planned.command_id,
                    label=planned.label,
                    command=planned.command,
                    cwd=planned.cwd,
                    started_at=started_at,
                    completed_at=started_at,
                    duration_ms=0,
                    exit_code=None,
                    status=planned.planned_status,
                    stdout_path=None,
                    stderr_path=None,
                    stdout_sha256=None,
                    stderr_sha256=None,
                    tool_name=planned.tool_name,
                    tool_version=tool_versions.get(planned.tool_name),
                    blocked_reason=planned.reason,
                )
            )
            continue

        commands_dir = commands_dirs[planned.lane]
        stdout_path = commands_dir / f"{planned.command_id}.stdout.txt"
        stderr_path = commands_dir / f"{planned.command_id}.stderr.txt"
        timer_started = time.monotonic()
        stdout_payload = b""
        stderr_payload = b""
        exit_code: int | None = None
        status = "failed_to_execute"
        blocked_reason: str | None = None
        try:
            completed = subprocess.run(
                planned.command,
                cwd=planned.cwd,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            stdout_payload = completed.stdout
            stderr_payload = completed.stderr
            exit_code = completed.returncode
            status = "passed" if completed.returncode in planned.success_exit_codes else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout_payload = exc.stdout or b""
            stderr_payload = exc.stderr or b""
            status = "timed_out"
            blocked_reason = f"Command timed out after {timeout_seconds}s."
        except OSError as exc:
            status = "failed_to_execute"
            blocked_reason = str(exc)

        duration_ms = int((time.monotonic() - timer_started) * 1000)
        completed_at = utc_now_text()

        stdout_written = None
        stderr_written = None
        stdout_sha = None
        stderr_sha = None
        if stdout_payload or stderr_payload or status in {"passed", "failed", "timed_out"}:
            stdout_written = _write_bytes(stdout_path, stdout_payload)
            stderr_written = _write_bytes(stderr_path, stderr_payload)
            stdout_sha = sha256_bytes(stdout_payload)
            stderr_sha = sha256_bytes(stderr_payload)

        results.append(
            CommandResult(
                lane=planned.lane,
                command_id=planned.command_id,
                label=planned.label,
                command=planned.command,
                cwd=planned.cwd,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                exit_code=exit_code,
                status=status,
                stdout_path=stdout_written,
                stderr_path=stderr_written,
                stdout_sha256=stdout_sha,
                stderr_sha256=stderr_sha,
                tool_name=planned.tool_name,
                tool_version=tool_versions.get(planned.tool_name),
                blocked_reason=blocked_reason,
            )
        )
    return results
