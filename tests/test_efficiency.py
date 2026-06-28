from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.validation import validate_run_dir
from tests.test_artifact_generation import init_git_repo


def write_efficiency_manifest(era_root: Path, repo_name: str, command: list[str], *, iterations: int = 3) -> None:
    manifests_dir = era_root / "config" / "workload_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"{repo_name.lower()}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "EfficiencyWorkloadManifest.v1",
                "repo_id": repo_name,
                "baseline_selection_policy": "latest_prior_efficiency_run",
                "workloads": [
                    {
                        "workload_id": "sleep_probe",
                        "label": "sleep probe",
                        "category": "runtime_benchmark",
                        "command": command,
                        "cwd_subpath": ".",
                        "runner": "internal_timer",
                        "iterations": iterations,
                        "regression_threshold_pct": 500.0,
                        "improvement_threshold_pct": 500.0,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_workload_allowlist(era_root: Path, executables: list[str]) -> None:
    config_dir = era_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "efficiency_workload_allowlist.json").write_text(
        json.dumps({"allowed_executables": executables}, indent=2) + "\n",
        encoding="utf-8",
    )


class EfficiencyTests(unittest.TestCase):
    def test_efficiency_without_manifest_is_unproven(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            run_dir = execute_run(
                repo_path=repo,
                lanes=["efficiency"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            review = (run_dir / "review.md").read_text(encoding="utf-8")
            baseline = json.loads((run_dir / "evidence" / "efficiency" / "baseline_artifact.json").read_text(encoding="utf-8"))
            self.assertIn("## Efficiency Lane", review)
            self.assertFalse(baseline["baseline_found"])
            self.assertIn("Classification: `unproven`", review)

    def test_efficiency_manifest_run_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(
                era_root,
                repo.name,
                ["python3", "-c", "import time; time.sleep(0.01)"],
            )
            run_dir = execute_run(
                repo_path=repo,
                lanes=["efficiency"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            bundle = json.loads(
                (run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json").read_text(encoding="utf-8")
            )
            result = validate_run_dir(run_dir)
            self.assertEqual(bundle["schema_version"], "EfficiencyEvidenceBundle.v1")
            self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_efficiency_second_run_uses_prior_run_as_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(
                era_root,
                repo.name,
                ["python3", "-c", "import time; time.sleep(0.01)"],
            )
            execute_run(
                repo_path=repo,
                lanes=["efficiency"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            second_run = execute_run(
                repo_path=repo,
                lanes=["efficiency"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            baseline = json.loads((second_run / "evidence" / "efficiency" / "baseline_artifact.json").read_text(encoding="utf-8"))
            statuses = {item["comparison_status"] for item in baseline["comparisons"]}
            self.assertTrue(baseline["baseline_found"])
            self.assertTrue(statuses.intersection({"within_range", "unstable", "improvement", "regression"}))

    def test_efficiency_missing_tool_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(
                era_root,
                repo.name,
                ["definitely_missing_tool_for_era", "--version"],
            )
            # Allowlist the sentinel so it reaches missing-tool detection rather
            # than being rejected at the allowlist gate first.
            write_workload_allowlist(era_root, ["definitely_missing_tool_for_era"])
            run_dir = execute_run(
                repo_path=repo,
                lanes=["efficiency"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            bundle = json.loads(
                (run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json").read_text(encoding="utf-8")
            )
            self.assertEqual(bundle["command_results"][0]["status"], "blocked_by_missing_tool")


class EfficiencyManifestHardeningTests(unittest.TestCase):
    def _run(self, era_root: Path, repo: Path) -> Path:
        return execute_run(
            repo_path=repo,
            lanes=["efficiency"],
            mode="full",
            artifacts_root=era_root / "artifacts" / "era-runs",
        )

    def test_cwd_subpath_escape_is_skipped_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            manifests_dir = era_root / "config" / "workload_manifests"
            manifests_dir.mkdir(parents=True, exist_ok=True)
            (manifests_dir / f"{repo.name.lower()}.json").write_text(
                json.dumps(
                    {
                        "schema_version": "EfficiencyWorkloadManifest.v1",
                        "repo_id": repo.name,
                        "workloads": [
                            {
                                "workload_id": "escape_probe",
                                "command": ["git", "status", "--short"],
                                "cwd_subpath": "../../../",
                                "runner": "internal_timer",
                                "iterations": 3,
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            run_dir = self._run(era_root, repo)
            bundle = json.loads(
                (run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json").read_text(encoding="utf-8")
            )
            result = bundle["command_results"][0]
            self.assertEqual(result["status"], "skipped")
            self.assertIsNone(result["exit_code"])
            self.assertIn("escapes the target repository", result["blocked_reason"])

    def test_unapproved_executable_is_skipped_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            # `bash` is not in the default allowlist and no override is provided.
            write_efficiency_manifest(era_root, repo.name, ["bash", "-c", "echo hi"])
            run_dir = self._run(era_root, repo)
            bundle = json.loads(
                (run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json").read_text(encoding="utf-8")
            )
            result = bundle["command_results"][0]
            self.assertEqual(result["status"], "skipped")
            self.assertIn("not in the efficiency workload allowlist", result["blocked_reason"])

    def test_manifest_provenance_hash_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(
                era_root,
                repo.name,
                ["python3", "-c", "import time; time.sleep(0.01)"],
            )
            run_dir = self._run(era_root, repo)
            manifest = json.loads(
                (run_dir / "evidence" / "efficiency" / "workload_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["manifest_status"], "loaded")
            self.assertIsInstance(manifest["manifest_sha256"], str)
            self.assertEqual(len(manifest["manifest_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
