from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.artifact_paths import build_run_paths, generate_run_id
from era_core.git_info import capture_git_snapshot, capture_target_manifest, detect_repo_id
from era_core.models import CommandResult


def init_git_repo(path: Path, branch: str = "main") -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-m", branch], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=ERA",
            "-c",
            "user.email=era@example.com",
            "commit",
            "-m",
            "init",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )


class ArtifactGenerationTests(unittest.TestCase):
    def test_run_id_generation(self) -> None:
        run_id = generate_run_id()
        self.assertRegex(run_id, r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")

    def test_artifact_paths_created_outside_target_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            target_repo = root / "target"
            target_repo.mkdir()
            artifacts_root = root / "era" / "artifacts" / "era-runs"
            paths = build_run_paths("test-run", artifacts_root)
            self.assertNotEqual(paths.root, target_repo)
            self.assertFalse(str(paths.root).startswith(str(target_repo)))

    def test_target_manifest_requires_commit_or_dirty_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            repo = Path(temp_root) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            snapshot = capture_git_snapshot(repo)
            with self.assertRaises(ValueError):
                capture_target_manifest(repo, detect_repo_id(repo), snapshot)

    def test_command_result_serialization(self) -> None:
        result = CommandResult(
            lane="accuracy",
            command_id="python_echo",
            label="python echo",
            command=["python", "-c", "print('ok')"],
            cwd="/tmp",
            started_at="2026-04-23T00:00:00Z",
            completed_at="2026-04-23T00:00:01Z",
            duration_ms=1000,
            exit_code=0,
            status="passed",
            stdout_path="/tmp/stdout.txt",
            stderr_path="/tmp/stderr.txt",
            stdout_sha256="a",
            stderr_sha256="b",
            tool_name="python",
            tool_version="3.x",
        )
        payload = result.to_dict()
        self.assertEqual(payload["command_id"], "python_echo")
        self.assertEqual(payload["status"], "passed")

    def test_review_markdown_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            era_root = Path(temp_root) / "era"
            repo = Path(temp_root) / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            run_dir = execute_run(
                repo_path=repo,
                lanes=["accuracy"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            review = (run_dir / "review.md").read_text(encoding="utf-8")
            self.assertIn("# ERA Review", review)
            self.assertIn("## Accuracy Lane", review)


if __name__ == "__main__":
    unittest.main()
