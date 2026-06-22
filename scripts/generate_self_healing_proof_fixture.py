#!/usr/bin/env python3
"""Generate the deterministic ERA Self-Healing proof fixture.

The ERA -> Centipede -> Self-Healing -> DoppelCore chain proof needs at least
one Self-Healing projection as stable input. A real ERA run only emits a
projection when the evaluated repository actually fails an accuracy gate, so a
green repository (the steady-state CI case) produces zero projections and the
chain proof has nothing to feed.

This script writes a committed, clearly-synthetic fixture bundle so the proof
has deterministic input without depending on a real failure. It is NOT part of
`era_cli run`: real runs stay honest and only project genuine, evidence-backed
findings. The fixture is built through the real ERA contract code paths
(`promote_normalized_results`, `build_findings_bundle`, `write_centipede_export`)
so it cannot drift away from the live bundle shape.

The bundle's identifiers are all derived from a single placeholder run id
(`FIXTURE_RUN_ID`). Consumers that import/feed the fixture against a persistent
DataForge-Local DB should substitute a fresh run id for that token so repeated
proofs never collide on already-consumed projections.

Run from the ERA repo root:

    python3 scripts/generate_self_healing_proof_fixture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from era_core.contracts import (  # noqa: E402
    build_era_scores,
    build_findings_bundle,
    build_tool_normalized_result,
    build_tool_raw_artifacts,
    promote_normalized_results,
)
from era_core.models import CommandResult  # noqa: E402
from era_integrations.centipede_export import write_centipede_export  # noqa: E402

FIXTURE_RUN_ID = "era-sh-chain-proof-fixture"
FIXTURE_COMMAND_ID = "era_self_healing_proof_gate"
FIXTURE_REPO_ID = "forge_command"
FIXTURE_COMMIT = "0000000000000000000000000000000000000000"
FIXTURE_TIMESTAMP = "2026-01-01T00:00:00Z"

FIXTURE_PATH = REPO_ROOT / "fixtures" / "self_healing_chain_proof" / "centipede_bundle.json"


def _synthetic_command_result() -> CommandResult:
    """A deterministic, clearly-synthetic failed accuracy command."""
    return CommandResult(
        lane="accuracy",
        command_id=FIXTURE_COMMAND_ID,
        label="ERA self-healing proof gate (synthetic fixture)",
        command=["era", "self-healing-proof", "--synthetic-fixture"],
        cwd="/synthetic/forge_command",
        started_at=FIXTURE_TIMESTAMP,
        completed_at=FIXTURE_TIMESTAMP,
        duration_ms=1,
        exit_code=1,
        status="failed",
        stdout_path="commands/accuracy/era_self_healing_proof_gate.stdout.txt",
        stderr_path="commands/accuracy/era_self_healing_proof_gate.stderr.txt",
        stdout_sha256="0" * 64,
        stderr_sha256="1" * 64,
        tool_name="era",
        tool_version="fixture",
        blocked_reason=None,
    )


def build_fixture_bundle() -> dict:
    command_result = _synthetic_command_result()
    command_results = [command_result]

    raw_artifacts = build_tool_raw_artifacts(FIXTURE_RUN_ID, command_results)
    normalized = build_tool_normalized_result(
        run_id=FIXTURE_RUN_ID,
        command_id=FIXTURE_COMMAND_ID,
        raw_artifact_refs=[item["raw_artifact_id"] for item in raw_artifacts],
        normalizer_name="era_self_healing_proof_fixture",
        normalizer_version="fixture",
        tool_name=command_result.tool_name,
        tool_version=command_result.tool_version,
        summary_status=command_result.status,
        parsed_findings=[
            {
                "finding_type": "accuracy_gate_failed",
                "summary": (
                    "SYNTHETIC FIXTURE: deterministic accuracy-gate failure used "
                    "only as stable input for the ERA self-healing chain proof."
                ),
                "target_files": [],
                "target_symbols": [],
                "risk_level": "high",
                "confidence": "high",
                "evidence_strength": "mechanical",
                "recommended_action": "operator_review",
                "blocked_reason": None,
                "lane_details": {
                    "command_id": command_result.command_id,
                    "command_label": command_result.label,
                    "command_status": command_result.status,
                    "exit_code": command_result.exit_code,
                    "synthetic_fixture": True,
                },
            }
        ],
        parse_warnings=[],
        parse_errors=[],
        created_at=FIXTURE_TIMESTAMP,
    )

    lane_drafts, findings = promote_normalized_results(
        run_id=FIXTURE_RUN_ID,
        repo_id=FIXTURE_REPO_ID,
        commit_sha=FIXTURE_COMMIT,
        normalized_results=[normalized],
        raw_artifacts=raw_artifacts,
        command_lanes={FIXTURE_COMMAND_ID: "accuracy"},
        default_target_files_by_lane={"accuracy": []},
        created_at=FIXTURE_TIMESTAMP,
    )

    era_scores = build_era_scores(
        run_id=FIXTURE_RUN_ID,
        repo_id=FIXTURE_REPO_ID,
        commit_sha=FIXTURE_COMMIT,
        lane_classifications={"accuracy": "failing"},
        command_results=command_results,
        lane_drafts=lane_drafts,
        findings=findings,
        overall_classification="failing",
        created_at=FIXTURE_TIMESTAMP,
    )

    findings_bundle = build_findings_bundle(
        run_id=FIXTURE_RUN_ID,
        repo_id=FIXTURE_REPO_ID,
        lane_drafts=lane_drafts,
        findings=findings,
        era_scores=era_scores,
        created_at=FIXTURE_TIMESTAMP,
    )

    evidence_bundles = {
        "accuracy": {
            "schema_version": "ERAEvidenceBundle.v1",
            "run_id": FIXTURE_RUN_ID,
            "repo_id": FIXTURE_REPO_ID,
            "lane": "accuracy",
            "command_results": [command_result.to_dict()],
            "tool_raw_artifacts": raw_artifacts,
            "tool_normalized_results": [normalized],
            "created_at": FIXTURE_TIMESTAMP,
        }
    }

    run_artifact = {
        "schema_version": "ERAEvaluationRun.v1",
        "run_id": FIXTURE_RUN_ID,
        "repo_id": FIXTURE_REPO_ID,
        "repo_path": "/synthetic/forge_command",
        "commit_sha": FIXTURE_COMMIT,
        "branch": "synthetic-fixture",
        "working_tree_status": "",
        "is_dirty": False,
        "lanes": ["accuracy"],
        "mode": "full",
        "baseline_ref": None,
        "baseline_commit": None,
        "started_at": FIXTURE_TIMESTAMP,
        "completed_at": FIXTURE_TIMESTAMP,
        "status": "completed_partial",
        "operator_requested_by": "era-self-healing-proof-fixture",
        "runner_version": "fixture",
        "tool_versions": {"era": "fixture"},
        "environment": {
            "platform": "synthetic-fixture",
            "python_version": "synthetic-fixture",
        },
        "evidence_bundle_refs": [],
        "finding_refs": [],
        "review_artifact_ref": None,
        "pre_run_git_status_short": "",
        "post_run_git_status_short": "",
        "pre_run_head": FIXTURE_COMMIT,
        "post_run_head": FIXTURE_COMMIT,
        "pre_run_dirty": False,
        "post_run_dirty": False,
        "read_only_invariant_status": "clean_verified",
        "read_only_invariant_notes": "Synthetic fixture: ERA did not touch any repository.",
    }

    # write_centipede_export validates the bundle before writing; an invalid
    # fixture raises here so the committed file is always import-ready.
    return write_centipede_export(
        run_artifact=run_artifact,
        selection_artifact=None,
        evidence_bundles=evidence_bundles,
        findings=findings_bundle,
        output_path=FIXTURE_PATH,
    )


def main() -> int:
    bundle = build_fixture_bundle()
    projection_count = len(bundle.get("self_healing_projections", []))
    if projection_count != 1:
        raise SystemExit(
            f"expected exactly 1 self-healing projection, got {projection_count}"
        )
    print(f"wrote {FIXTURE_PATH.relative_to(REPO_ROOT)} ({projection_count} projection)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
