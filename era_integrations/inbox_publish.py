"""Publish an evaluation export to the DataForge Local inbox (ERA-PUB-01).

Company Core Six, principle 6: automate up to the decision. After a run that
produced an ``era_evaluation_export`` artifact, ERA copies it into the inbox that
DataForge Local scans. DataForge Local stores it and Forge_Command shows it. The
operator decides. Nothing here approves or acts.

Boundaries:
- ERA writes only a finished file, by temporary file and rename, into a directory
  that already exists. ERA never creates a directory in another system's tree and
  never writes to DataForge Local itself.
- Fail closed. A missing, symlinked, foreign-owned, or group- or world-writable
  inbox is skipped and the reason is reported. The envelope ``signature`` is an
  unsigned digest reference, so the inbox permission is the producer check on the
  other side. ERA will not weaken it by publishing into an unsafe directory.
- A skip never fails the run. The run's own evidence is complete without it.
- The inbox location is the shared convention ``DFL_ERA_DROP_DIR``, default
  ``~/.dataforge-local/era-inbox``.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ENV_DROP_DIR = "DFL_ERA_DROP_DIR"
DEFAULT_INBOX = "~/.dataforge-local/era-inbox"
EXPORT_FILENAME = "evaluation_export.json"
RECEIPT_FILENAME = "publish_receipt.json"
FAMILY = "era_evaluation_export"
MAX_STORE_BYTES = 256 * 1024  # DataForge Local's PS_MAX_PAYLOAD_BYTES. A larger artifact would be refused there.


@dataclass
class PublishResult:
    status: str  # "published" or "skipped"
    reason: str
    run_id: str | None = None
    inbox: str | None = None
    path: str | None = None
    published_at: str | None = None

    def line(self) -> str:
        detail = self.path if self.status == "published" else self.reason
        return f"era export {self.status}: {detail}"


def resolve_inbox(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get(ENV_DROP_DIR) or DEFAULT_INBOX).expanduser()


def _inbox_problem(inbox: Path) -> str | None:
    if inbox.is_symlink():
        return "inbox_unsafe: the inbox is a symlink"
    if not inbox.exists():
        return "inbox_missing: the inbox does not exist (ERA never creates it)"
    info = os.lstat(inbox)
    if not stat.S_ISDIR(info.st_mode):
        return "inbox_unsafe: the inbox is not a directory"
    if info.st_uid != os.getuid():
        return "inbox_unsafe: the inbox is owned by another user"
    if info.st_mode & 0o022:
        return f"inbox_unsafe: the inbox is group- or world-writable (mode {stat.S_IMODE(info.st_mode):04o})"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _receipt(run_dir: Path, result: PublishResult) -> PublishResult:
    """Record the outcome next to the run. It is an operational receipt, outside the evidence hash chain."""
    try:
        (run_dir / RECEIPT_FILENAME).write_text(json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass
    return result


def publish_export(run_dir: Path, environ: dict[str, str] | None = None) -> PublishResult:
    """Copy the run's export into the inbox. Never raises for a skip. Returns what happened."""
    source = run_dir / EXPORT_FILENAME
    if not source.is_file():
        return _receipt(run_dir, PublishResult("skipped", "no_export: the run has no evaluation export"))
    inbox = resolve_inbox(environ)
    problem = _inbox_problem(inbox)
    if problem:
        return _receipt(run_dir, PublishResult("skipped", problem, inbox=str(inbox)))

    try:
        raw = source.read_bytes()
        artifact = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return _receipt(run_dir, PublishResult("skipped", "export_unreadable: the export is not valid JSON", inbox=str(inbox)))
    if not isinstance(artifact, dict) or artifact.get("artifact_family") != FAMILY:
        return _receipt(run_dir, PublishResult("skipped", f"wrong_family: the file is not an {FAMILY} artifact", inbox=str(inbox)))
    size = len(json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    run_id = str(artifact.get("payload", {}).get("run_id", run_dir.name))
    if size > MAX_STORE_BYTES:
        return _receipt(
            run_dir,
            PublishResult("skipped", f"export_too_large: {size} bytes exceeds the store limit {MAX_STORE_BYTES}", run_id, str(inbox)),
        )

    final = inbox / f"{FAMILY}.{run_id}.json"
    temporary = inbox / f".{final.name}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, final)
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        return _receipt(run_dir, PublishResult("skipped", f"write_failed: {error}", run_id, str(inbox)))
    return _receipt(run_dir, PublishResult("published", "published", run_id, str(inbox), str(final), _now()))
