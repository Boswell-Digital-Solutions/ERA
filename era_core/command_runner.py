from __future__ import annotations

import statistics
import subprocess
import time
from pathlib import Path

from era_core.artifact_paths import utc_now_text
from era_core.hashing import sha256_bytes
from era_core.models import CommandResult, PlannedCommand
from era_core.sandbox import Sandbox


def _write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def run_planned_commands(
    planned_commands: list[PlannedCommand],
    commands_dirs: dict[str, Path],
    tool_versions: dict[str, str],
    timeout_seconds: int = 1800,
    sandbox: Sandbox | None = None,
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
                    lane_metadata=planned.lane_metadata,
                )
            )
            continue

        commands_dir = commands_dirs[planned.lane]
        stdout_path = commands_dir / f"{planned.command_id}.stdout.txt"
        stderr_path = commands_dir / f"{planned.command_id}.stderr.txt"
        overall_timer_started = time.monotonic()
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        exit_code: int | None = None
        status = "failed_to_execute"
        blocked_reason: str | None = None
        iteration_durations_ms: list[int] = []
        lane_metadata = dict(planned.lane_metadata or {})
        iterations_requested = max(1, planned.iterations)

        # When a sandbox is active, run the target's own command contained
        # (no external network; the target tree is overlay-protected). The
        # recorded command stays the real command; only execution is wrapped.
        exec_argv = sandbox.wrap(planned.command, planned.cwd) if sandbox else planned.command

        for iteration_index in range(iterations_requested):
            timer_started = time.monotonic()
            try:
                completed = subprocess.run(
                    exec_argv,
                    cwd=planned.cwd,
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout_chunks.append(completed.stdout)
                stderr_chunks.append(completed.stderr)
                exit_code = completed.returncode
                status = "passed" if completed.returncode in planned.success_exit_codes else "failed"
            except subprocess.TimeoutExpired as exc:
                stdout_chunks.append(exc.stdout or b"")
                stderr_chunks.append(exc.stderr or b"")
                status = "timed_out"
                blocked_reason = f"Command timed out after {timeout_seconds}s."
            except OSError as exc:
                status = "failed_to_execute"
                blocked_reason = str(exc)

            iteration_durations_ms.append(int((time.monotonic() - timer_started) * 1000))
            if status != "passed":
                break

        duration_ms = int((time.monotonic() - overall_timer_started) * 1000)
        completed_at = utc_now_text()

        stdout_payload = b""
        stderr_payload = b""
        if stdout_chunks or stderr_chunks:
            if len(stdout_chunks) <= 1:
                stdout_payload = stdout_chunks[0] if stdout_chunks else b""
                stderr_payload = stderr_chunks[0] if stderr_chunks else b""
            else:
                stdout_payload = b"".join(
                    [
                        b"".join(
                            [
                                f"--- iteration {index + 1} ---\n".encode("utf-8"),
                                chunk,
                                b"\n",
                            ]
                        )
                        for index, chunk in enumerate(stdout_chunks)
                    ]
                )
                stderr_payload = b"".join(
                    [
                        b"".join(
                            [
                                f"--- iteration {index + 1} ---\n".encode("utf-8"),
                                chunk,
                                b"\n",
                            ]
                        )
                        for index, chunk in enumerate(stderr_chunks)
                    ]
                )

        stdout_written = None
        stderr_written = None
        stdout_sha = None
        stderr_sha = None
        if stdout_payload or stderr_payload or status in {"passed", "failed", "timed_out"}:
            stdout_written = _write_bytes(stdout_path, stdout_payload)
            stderr_written = _write_bytes(stderr_path, stderr_payload)
            stdout_sha = sha256_bytes(stdout_payload)
            stderr_sha = sha256_bytes(stderr_payload)

        lane_metadata["iterations_requested"] = iterations_requested
        lane_metadata["iterations_completed"] = len(iteration_durations_ms)
        lane_metadata["iteration_durations_ms"] = iteration_durations_ms
        if iteration_durations_ms:
            lane_metadata["timing_summary"] = {
                "min_ms": min(iteration_durations_ms),
                "max_ms": max(iteration_durations_ms),
                "mean_ms": round(sum(iteration_durations_ms) / len(iteration_durations_ms), 3),
                "median_ms": statistics.median(iteration_durations_ms),
                "stdev_ms": round(statistics.stdev(iteration_durations_ms), 3)
                if len(iteration_durations_ms) >= 2
                else 0.0,
            }
            mean_ms = lane_metadata["timing_summary"]["mean_ms"]
            if len(iteration_durations_ms) < 2:
                variance_classification = "single_sample"
            elif mean_ms == 0:
                variance_classification = "stable"
            else:
                coefficient = lane_metadata["timing_summary"]["stdev_ms"] / mean_ms
                if coefficient < 0.05:
                    variance_classification = "stable"
                elif coefficient < 0.15:
                    variance_classification = "moderate_variance"
                else:
                    variance_classification = "unstable"
            lane_metadata["variance_classification"] = variance_classification

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
                lane_metadata=lane_metadata or None,
            )
        )
    return results
