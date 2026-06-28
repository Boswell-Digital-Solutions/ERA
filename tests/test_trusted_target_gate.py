from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import (
    OPERATOR_TRUSTED,
    UNTRUSTED,
    UntrustedTargetError,
    execute_run,
)
from tests.test_artifact_generation import init_git_repo


class TrustedTargetGateTests(unittest.TestCase):
    def test_untrusted_target_fails_closed_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            artifacts_root = era_root / "artifacts" / "era-runs"

            with self.assertRaises(UntrustedTargetError):
                execute_run(
                    repo_path=repo,
                    lanes=["accuracy"],
                    mode="full",
                    artifacts_root=artifacts_root,
                    target_trust=UNTRUSTED,
                )

            # Fail-closed: ERA must not have created any run artifacts.
            self.assertFalse(
                artifacts_root.exists() and any(artifacts_root.iterdir()),
                "untrusted run must not write artifacts",
            )

    def test_trusted_run_records_execution_posture(self) -> None:
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
                target_trust=OPERATOR_TRUSTED,
            )
            run_artifact = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            posture = run_artifact["execution_posture"]
            self.assertTrue(posture["executes_target_code"])
            self.assertEqual(posture["sandbox"], "none")
            self.assertEqual(posture["target_trust"], OPERATOR_TRUSTED)
            self.assertEqual(
                run_artifact["read_only_invariant_scope"], "target_git_tree_only"
            )


if __name__ == "__main__":
    unittest.main()
