from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_export import (
    AUTHORITY_STATEMENT,
    EXPORT_FILENAME,
    EXPORT_SCHEMA,
    build_evaluation_export,
    validate_evaluation_export,
)
from era_core.hashing import sha256_json, sha256_path, write_json
from era_core.validation import validate_run_dir
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_validation import EVAL, FAST, SLOW, ValidationBase, refresh_entries
from tests.test_efficiency import write_efficiency_manifest


def reseal(payload: dict) -> dict:
    payload["sha256"] = sha256_json({k: v for k, v in payload.items() if k != "sha256"})
    return payload


class ExportContentTests(ValidationBase):
    def export(self, run_dir: Path) -> dict:
        return json.loads((run_dir / EXPORT_FILENAME).read_text(encoding="utf-8"))

    def test_export_summarizes_the_run_and_states_its_authority(self) -> None:
        first, second = self.make_runs()
        data = self.export(second)
        comparison = self.read(second, "comparison.json")
        self.assertEqual(data["schema_version"], EXPORT_SCHEMA)
        self.assertEqual(data["run_id"], second.name)
        self.assertEqual(data["authority"], AUTHORITY_STATEMENT)
        self.assertEqual(data["consumer_contract_status"], "local_to_era")
        self.assertEqual(data["execution_posture"]["sandbox"], "none")
        (workload,) = data["workloads"]
        self.assertEqual(workload["workload_id"], "eval_probe")
        self.assertEqual(workload["claim_status"], comparison["claim_status"])
        self.assertEqual(workload["baseline_run_id"], first.name)
        self.assertEqual(workload["isolation_status"], "not_required")
        self.assertIn("median_ms", workload["metrics"])
        self.assertEqual(
            set(workload["artifacts"]), {"fingerprint", "quality_gate", "metric_vector", "isolation_receipt", "comparison"}
        )
        for kind, ref in workload["artifacts"].items():
            self.assertEqual(json.loads((second / ref["path"]).read_text(encoding="utf-8"))["sha256"], ref["sha256"], kind)

    def test_export_is_deterministic_and_hash_chained(self) -> None:
        _, second = self.make_runs()
        self.assertEqual(build_evaluation_export(second), self.export(second))
        chain = json.loads((second / "hashes.json").read_text(encoding="utf-8"))["evidence_hash_chain"]
        self.assertEqual(chain["evaluation_export"]["sha256"], self.export(second)["sha256"])
        self.assertTrue(any(e["path"] == EXPORT_FILENAME for e in json.loads((second / "hashes.json").read_text())["entries"]))

    def test_blocked_runs_export_their_reasons(self) -> None:
        _, second = self.make_runs(first=(0.95, SLOW), second=(0.2, FAST))
        (workload,) = self.export(second)["workloads"]
        self.assertEqual((workload["claim_status"], workload["quality_status"]), ("quality_blocked", "failed"))
        self.assertTrue(workload["blocked_reasons"])
        self.assertEqual(workload["efficiency_status"], "not_evaluated")

    def test_rejected_baselines_export_only_their_reasons(self) -> None:
        _, second = self.make_runs(first=(0.1, SLOW), second=(0.95, FAST))
        (workload,) = self.export(second)["workloads"]
        self.assertEqual(workload["claim_status"], "no_baseline")
        self.assertEqual(workload["baseline_rejection_reasons"], ["quality_failed"])

    def test_legacy_runs_have_no_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            era_root, repo = root / "era", root / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(era_root, repo.name, ["python3", "-c", "pass"])
            run_dir = execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
            self.assertFalse((run_dir / EXPORT_FILENAME).exists())
            self.assertIsNone(build_evaluation_export(run_dir))
            hashes = json.loads((run_dir / "hashes.json").read_text(encoding="utf-8"))
            self.assertNotIn("evaluation_export", hashes["evidence_hash_chain"])
            self.assertTrue(validate_run_dir(run_dir)["ok"])


class ExportValidationTests(ValidationBase):
    def path(self, run_dir: Path) -> Path:
        return run_dir / EXPORT_FILENAME

    def load(self, run_dir: Path) -> dict:
        return json.loads(self.path(run_dir).read_text(encoding="utf-8"))

    def test_intact_export_validates(self) -> None:
        _, second = self.make_runs()
        self.assertTrue(validate_run_dir(second)["ok"])

    def test_a_resealed_claim_edit_is_caught_by_the_rebuild(self) -> None:
        _, second = self.make_runs(second=(0.2, FAST))
        forged = self.load(second)
        forged["workloads"][0]["claim_status"] = "permitted"
        forged["workloads"][0]["efficiency_status"] = "improvement"
        write_json(self.path(second), reseal(forged))
        refresh_entries(second)
        self.assertBlocked(second, "differs from the run evidence")

    def test_a_changed_authority_statement_is_caught(self) -> None:
        _, second = self.make_runs()
        forged = self.load(second)
        forged["authority"] = "Canonical truth."
        write_json(self.path(second), reseal(forged))
        refresh_entries(second)
        self.assertBlocked(second, "authority statement was changed")

    def test_a_stale_chain_reference_is_caught(self) -> None:
        _, second = self.make_runs()
        hashes = json.loads((second / "hashes.json").read_text(encoding="utf-8"))
        hashes["evidence_hash_chain"]["evaluation_export"]["sha256"] = "0" * 64
        write_json(second / "hashes.json", hashes)
        self.assertBlocked(second, "stale evaluation export reference")

    def test_a_missing_export_or_chain_entry_is_caught(self) -> None:
        _, second = self.make_runs()
        self.path(second).unlink()
        refresh_entries(second)
        self.assertBlocked(second, "missing or not valid JSON")
        _, third = self.make_runs()
        hashes = json.loads((third / "hashes.json").read_text(encoding="utf-8"))
        del hashes["evidence_hash_chain"]["evaluation_export"]
        write_json(third / "hashes.json", hashes)
        self.assertBlocked(third, "missing the evaluation export")

    def test_an_edited_source_artifact_changes_the_rebuild(self) -> None:
        _, second = self.make_runs()
        comparison = self.read(second, "comparison.json")
        comparison["blocked_reasons"] = ["edited"]
        write_json(second / EVAL / "comparison.json", reseal(comparison))
        refresh_entries(second)
        result = validate_run_dir(second)
        self.assertFalse(result["ok"])

    def test_an_export_without_workloads_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            era_root, repo = root / "era", root / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(era_root, repo.name, ["python3", "-c", "pass"])
            run_dir = execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
            (run_dir / EXPORT_FILENAME).write_text("{}", encoding="utf-8")
            errors = validate_evaluation_export(run_dir, {})
            self.assertTrue(any("no opted-in workload" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
