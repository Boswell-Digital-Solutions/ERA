from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.redundancy import (
    apply_redundancy_tooling,
    build_redundancy_normalized_results,
    detect_redundancy_commands,
    load_intentional_redundancy_exceptions,
)
from era_core.models import CommandResult
from tests.test_artifact_generation import init_git_repo


class RedundancyTests(unittest.TestCase):
    def test_redundancy_command_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            repo = Path(temp_root)
            (repo / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
            (repo / "src-tauri").mkdir()
            (repo / "src-tauri" / "Cargo.toml").write_text("[package]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
            commands = detect_redundancy_commands(repo)
            self.assertEqual([item.command_id for item in commands], ["jscpd_scan", "knip_scan", "cargo_tree_duplicates"])
            self.assertTrue(all(item.lane == "redundancy" for item in commands))

    def test_missing_redundancy_tools_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            repo = Path(temp_root)
            (repo / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
            commands = detect_redundancy_commands(repo)
            planned = apply_redundancy_tooling(
                commands,
                [
                    {"tool": "jscpd", "status": "missing"},
                    {"tool": "knip", "status": "missing"},
                    {"tool": "cargo", "status": "not_applicable"},
                ],
            )
            blocked = [item for item in planned if item.execute is False]
            self.assertTrue(blocked)
            self.assertTrue(all(item.planned_status in {"blocked_by_missing_tool", "skipped"} for item in blocked))

    def test_exception_file_marks_redundancy_as_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            (era_root / "config").mkdir(parents=True)
            (era_root / "config" / "intentional_redundancy_exceptions.json").write_text(
                json.dumps(
                    {
                        "exceptions": [
                            {
                                "schema_version": "IntentionalRedundancyException.v1",
                                "exception_id": "ex-1",
                                "repo_id": "repo-1",
                                "file_paths": ["src/generated/file.ts"],
                                "symbol_refs": [],
                                "reason": "Generated mirror file",
                                "approved_by": "operator",
                                "approved_at": "2026-04-24T00:00:00Z",
                                "review_after": "2026-05-24T00:00:00Z",
                                "source_finding_id": "finding-1",
                                "evidence_refs": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            exceptions = load_intentional_redundancy_exceptions("repo-1", era_root=era_root)
            stdout_path = temp_path / "stdout.txt"
            stderr_path = temp_path / "stderr.txt"
            stdout_path.write_text("Duplicate code found in src/generated/file.ts\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            results = [
                CommandResult(
                    lane="redundancy",
                    command_id="jscpd_scan",
                    label="jscpd scan",
                    command=["jscpd", "."],
                    cwd=str(temp_path),
                    started_at="2026-04-24T00:00:00Z",
                    completed_at="2026-04-24T00:00:01Z",
                    duration_ms=1000,
                    exit_code=0,
                    status="passed",
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    stdout_sha256="hash-a",
                    stderr_sha256="hash-b",
                    tool_name="jscpd",
                    tool_version="1.0.0",
                    blocked_reason=None,
                )
            ]
            raw_artifacts = [
                {"raw_artifact_id": "jscpd_scan:stdout", "command_id": "jscpd_scan", "sha256": "hash-a"},
                {"raw_artifact_id": "jscpd_scan:stderr", "command_id": "jscpd_scan", "sha256": "hash-b"},
            ]
            normalized = build_redundancy_normalized_results(
                run_id="run-1",
                command_results=results,
                raw_artifacts=raw_artifacts,
                exceptions=exceptions["exceptions"],
                normalizer_version="0.1.0",
            )
            self.assertEqual(normalized[0]["parsed_findings"][0]["finding_type"], "ignored_with_reason")

    def test_redundancy_only_run_writes_redundancy_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            (repo / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
            run_dir = execute_run(
                repo_path=repo,
                lanes=["redundancy"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            bundle = json.loads(
                (run_dir / "evidence" / "redundancy" / "redundancy_evidence_bundle.json").read_text(encoding="utf-8")
            )
            review = (run_dir / "review.md").read_text(encoding="utf-8")
            self.assertEqual(bundle["schema_version"], "RedundancyEvidenceBundle.v1")
            self.assertIn("## Redundancy Lane", review)


if __name__ == "__main__":
    unittest.main()
