from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class PlannedCommand:
    lane: str
    command_id: str
    label: str
    command: list[str]
    cwd: str
    tool_name: str
    execute: bool = True
    planned_status: str = "planned"
    reason: str | None = None
    success_exit_codes: tuple[int, ...] = (0,)


@dataclass
class CommandResult:
    lane: str
    command_id: str
    label: str
    command: list[str]
    cwd: str
    started_at: str
    completed_at: str
    duration_ms: int
    exit_code: int | None
    status: str
    stdout_path: str | None
    stderr_path: str | None
    stdout_sha256: str | None
    stderr_sha256: str | None
    tool_name: str
    tool_version: str | None
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
