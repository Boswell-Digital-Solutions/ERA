from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


def resolve_era_root() -> Path:
    env_root = os.getenv("ERA_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


def default_artifacts_root(era_root: Path | None = None) -> Path:
    return (era_root or resolve_era_root()) / "artifacts" / "era-runs"


@dataclass(frozen=True)
class RunPaths:
    root: Path
    evidence_dir: Path
    accuracy_dir: Path
    redundancy_dir: Path
    accuracy_commands_dir: Path
    redundancy_commands_dir: Path
    run_json: Path
    target_manifest: Path
    tool_availability: Path
    test_selection: Path
    review: Path
    hashes: Path
    findings: Path
    test_evidence_bundle: Path
    redundancy_evidence_bundle: Path
    centipede_bundle: Path


def build_run_paths(run_id: str, artifacts_root: Path | None = None) -> RunPaths:
    root = (artifacts_root or default_artifacts_root()).resolve() / run_id
    evidence_dir = root / "evidence"
    accuracy_dir = evidence_dir / "accuracy"
    redundancy_dir = evidence_dir / "redundancy"
    accuracy_commands_dir = accuracy_dir / "commands"
    redundancy_commands_dir = redundancy_dir / "commands"
    return RunPaths(
        root=root,
        evidence_dir=evidence_dir,
        accuracy_dir=accuracy_dir,
        redundancy_dir=redundancy_dir,
        accuracy_commands_dir=accuracy_commands_dir,
        redundancy_commands_dir=redundancy_commands_dir,
        run_json=root / "run.json",
        target_manifest=root / "target_manifest.json",
        tool_availability=root / "tool_availability.json",
        test_selection=root / "test_selection_artifact.json",
        review=root / "review.md",
        hashes=root / "hashes.json",
        findings=root / "findings.json",
        test_evidence_bundle=accuracy_dir / "test_evidence_bundle.json",
        redundancy_evidence_bundle=redundancy_dir / "redundancy_evidence_bundle.json",
        centipede_bundle=root / "centipede_bundle.json",
    )


def ensure_run_dirs(paths: RunPaths) -> None:
    for directory in (
        paths.root,
        paths.evidence_dir,
        paths.accuracy_dir,
        paths.redundancy_dir,
        paths.accuracy_commands_dir,
        paths.redundancy_commands_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def find_latest_run(artifacts_root: Path | None = None) -> Path:
    runs_root = (artifacts_root or default_artifacts_root()).resolve()
    candidates = [path for path in runs_root.iterdir() if path.is_dir() and (path / "run.json").exists()]
    if not candidates:
        raise FileNotFoundError(f"No ERA runs found under {runs_root}")
    return sorted(candidates)[-1]
