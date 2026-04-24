from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.validation import validate_run_dir
from tests.test_artifact_generation import init_git_repo


class ValidationTests(unittest.TestCase):
    def test_validation_fails_when_required_artifact_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            run_dir = execute_run(
                repo_path=repo,
                lanes=["accuracy"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            (run_dir / "review.md").unlink()
            result = validate_run_dir(run_dir)
            self.assertFalse(result["ok"])
            self.assertTrue(any("review.md" in err for err in result["errors"]))

    def test_validation_supports_redundancy_only_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            run_dir = execute_run(
                repo_path=repo,
                lanes=["redundancy"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
            )
            result = validate_run_dir(run_dir)
            self.assertTrue(result["ok"], msg="\n".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
