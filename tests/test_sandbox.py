from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import UNTRUSTED, execute_run
from era_core.sandbox import MODE_AUTO, MODE_OFF, unshare_containment_usable
from tests.test_efficiency import write_efficiency_manifest
from tests.test_artifact_generation import init_git_repo

_SANDBOX_AVAILABLE = unshare_containment_usable()


@unittest.skipUnless(_SANDBOX_AVAILABLE, "unshare/overlay containment not available on this host")
class SandboxContainmentTests(unittest.TestCase):
    def test_contained_run_allows_untrusted_and_records_posture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            # Untrusted target, but a usable sandbox -> the gate is satisfied by
            # containment and the run proceeds without --trusted-target.
            run_dir = execute_run(
                repo_path=repo,
                lanes=["accuracy"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
                target_trust=UNTRUSTED,
                sandbox_mode=MODE_AUTO,
            )
            run_artifact = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            posture = run_artifact["execution_posture"]
            self.assertEqual(posture["sandbox"], "contained")
            self.assertEqual(posture["network"], "isolated")
            self.assertEqual(posture["target_filesystem"], "overlay_protected")
            self.assertEqual(posture["target_trust"], UNTRUSTED)
            self.assertEqual(run_artifact["read_only_invariant_scope"], "enforced_by_overlay")

    def test_sandbox_protects_real_repo_from_target_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            # A workload that tries to write a file into the target repo cwd.
            write_efficiency_manifest(
                era_root,
                repo.name,
                ["python3", "-c", "open('SANDBOX_LEAK.txt', 'w').write('leak')"],
            )
            run_dir = execute_run(
                repo_path=repo,
                lanes=["efficiency"],
                mode="full",
                artifacts_root=era_root / "artifacts" / "era-runs",
                target_trust=UNTRUSTED,
                sandbox_mode=MODE_AUTO,
            )
            bundle = json.loads(
                (run_dir / "evidence" / "efficiency" / "efficiency_evidence_bundle.json").read_text(
                    encoding="utf-8"
                )
            )
            # The workload ran (it wrote into the overlay, so it succeeded)...
            self.assertEqual(bundle["command_results"][0]["status"], "passed")
            # ...but the real target repo must be untouched.
            self.assertFalse(
                (repo / "SANDBOX_LEAK.txt").exists(),
                "sandbox must keep target writes out of the real repo",
            )


class SandboxModeTests(unittest.TestCase):
    def test_no_sandbox_untrusted_still_fails_closed(self) -> None:
        from era_cli.commands.run import UntrustedTargetError

        with tempfile.TemporaryDirectory() as temp_root:
            temp_path = Path(temp_root)
            era_root = temp_path / "era"
            repo = temp_path / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            with self.assertRaises(UntrustedTargetError):
                execute_run(
                    repo_path=repo,
                    lanes=["accuracy"],
                    mode="full",
                    artifacts_root=era_root / "artifacts" / "era-runs",
                    target_trust=UNTRUSTED,
                    sandbox_mode=MODE_OFF,
                )


if __name__ == "__main__":
    unittest.main()
