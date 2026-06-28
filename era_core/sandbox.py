from __future__ import annotations

import functools
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

# Sandbox levels.
SANDBOX_NONE = "none"
SANDBOX_CONTAINED = "contained"

# Sandbox modes requestable by callers / the CLI.
MODE_AUTO = "auto"
MODE_OFF = "off"

# ERA executes the target's own commands. A "contained" run wraps each command in
# a Linux namespace that (1) has no external network and (2) presents the target
# repository through an overlay so the real working tree is physically immutable
# while builds can still write (their writes land in a throwaway upper layer).
# This is build-compatible (cargo test can still write target/, node_modules,
# dist) yet removes the two worst risks of running an untrusted target: network
# exfiltration and durable mutation of the target.
#
# Residual, disclosed limitation: the namespace still sees the rest of the host
# filesystem, so a contained run is not a full jail (a target could still read
# host paths). It is a large, real risk reduction appropriate for ERA's internal
# single-operator model; a full filesystem jail (e.g. bubblewrap) is future work.


def _overlay_script(command: list[str], cwd: str, upper: str, work: str) -> str:
    quoted_cmd = " ".join(shlex.quote(part) for part in command)
    return " && ".join(
        [
            "set -e",
            f"mkdir -p {shlex.quote(upper)} {shlex.quote(work)}",
            "mount -t overlay overlay -o "
            f"lowerdir={shlex.quote(cwd)},upperdir={shlex.quote(upper)},workdir={shlex.quote(work)} "
            f"{shlex.quote(cwd)}",
            f"cd {shlex.quote(cwd)}",
            f"exec {quoted_cmd}",
        ]
    )


def _unshare_argv(inner_script: str) -> list[str]:
    # -r map current user to root inside the namespace (needed to mount)
    # -n new (empty) network namespace -> no external network
    # -m new mount namespace -> overlay mount is private and torn down with it
    return ["unshare", "-r", "-n", "-m", "--", "/bin/sh", "-c", inner_script]


@functools.lru_cache(maxsize=1)
def unshare_containment_usable() -> bool:
    """Probe whether unshare + user-namespace + overlay actually work here.

    Cached. Returns True only if a trivial contained command succeeds, so hosts
    where unshare exists but user namespaces or overlayfs are restricted fall
    back cleanly instead of producing spurious command failures.
    """
    if not shutil.which("unshare"):
        return False
    probe_root: str | None = None
    try:
        probe_root = tempfile.mkdtemp(prefix="era-sandbox-probe-")
        lower = Path(probe_root) / "lower"
        upper = Path(probe_root) / "up"
        work = Path(probe_root) / "work"
        lower.mkdir()
        script = _overlay_script(["true"], str(lower), str(upper), str(work))
        completed = subprocess.run(
            _unshare_argv(script),
            capture_output=True,
            timeout=30,
            check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if probe_root:
            shutil.rmtree(probe_root, ignore_errors=True)


class Sandbox:
    """A contained-execution backend for target commands."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        self.level = SANDBOX_CONTAINED
        self.network = "isolated"
        self.target_filesystem = "overlay_protected"
        self._scratch_dirs: list[str] = []

    def posture(self) -> dict[str, object]:
        return {
            "sandbox": self.level,
            "sandbox_backend": self.backend,
            "network": self.network,
            "target_filesystem": self.target_filesystem,
        }

    def wrap(self, command: list[str], cwd: str) -> list[str]:
        """Return the argv that runs ``command`` (with working dir ``cwd``) contained."""
        scratch = tempfile.mkdtemp(prefix="era-sandbox-")
        self._scratch_dirs.append(scratch)
        upper = str(Path(scratch) / "up")
        work = str(Path(scratch) / "work")
        return _unshare_argv(_overlay_script(command, cwd, upper, work))

    def cleanup(self) -> None:
        for scratch in self._scratch_dirs:
            shutil.rmtree(scratch, ignore_errors=True)
        self._scratch_dirs.clear()


def resolve_sandbox(mode: str) -> Sandbox | None:
    """Resolve a sandbox for the requested mode.

    ``MODE_AUTO`` returns a contained Sandbox when a usable backend is detected,
    otherwise None. ``MODE_OFF`` / ``SANDBOX_NONE`` always return None.
    """
    if mode in (MODE_OFF, SANDBOX_NONE):
        return None
    if mode == MODE_AUTO:
        if unshare_containment_usable():
            return Sandbox(backend="unshare")
        return None
    raise ValueError(f"Unknown sandbox mode: {mode}")


def none_posture() -> dict[str, object]:
    return {
        "sandbox": SANDBOX_NONE,
        "sandbox_backend": "none",
        "network": "host",
        "target_filesystem": "writable",
    }
