from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_contract_export import AUTHORITY, payload_digest
from era_core.eval_export import (
    EXPORT_FILENAME,
    EXPORT_SCHEMA,
    build_evaluation_export,
    export_reference,
    validate_evaluation_export,
)
from era_core.hashing import write_json
from era_core.validation import validate_run_dir
from tests.test_artifact_generation import init_git_repo
from tests.test_efficiency import write_efficiency_manifest
from tests.test_eval_validation import EVAL, FAST, SLOW, ValidationBase, refresh_entries


def reseal(artifact: dict) -> dict:
    """Recompute the payload digest and the envelope references, as a forger who edits the payload would."""
    artifact["payload"]["payload_digest"] = payload_digest(artifact["payload"])
    artifact["signature"] = "unsigned:" + artifact["payload"]["payload_digest"]
    return artifact


class ExportContentTests(ValidationBase):
    def export(self, run_dir: Path) -> dict:
        return json.loads((run_dir / EXPORT_FILENAME).read_text(encoding="utf-8"))

    def test_export_is_the_admitted_artifact_and_states_its_authority(self) -> None:
        first, second = self.make_runs()
        artifact = self.export(second)
        payload = artifact["payload"]
        comparison = self.read(second, "comparison.json")
        self.assertEqual(artifact["artifact_family"], "era_evaluation_export")
        self.assertEqual((artifact["produced_by_system"], artifact["promotion_class"]), ("ERA", "local_only"))
        self.assertEqual((artifact["sensitivity_class"], artifact["visibility_class"]), ("internal", "operator"))
        self.assertTrue(artifact["signature"].startswith("unsigned:sha256:"))
        self.assertEqual(payload["schema_version"], EXPORT_SCHEMA)
        self.assertEqual(payload["run_id"], second.name)
        self.assertEqual(payload["authority"], AUTHORITY)
        self.assertEqual(
            set(payload["execution_posture"]), {"sandbox", "sandbox_backend", "network", "target_filesystem", "target_trust"}
        )
        (workload,) = payload["workloads"]
        self.assertEqual(workload["claim_status"], comparison["claim_status"])
        self.assertEqual(workload["baseline_run_id"], first.name)
        self.assertEqual(workload["isolation_status"], "not_required")
        self.assertRegex(workload["metrics"]["median_ms"]["value"], r"^(0|[1-9][0-9]*(\.[0-9]*[1-9])?)$")
        self.assertEqual(workload["metrics"]["median_ms"]["aggregation"], "median")
        self.assertEqual(
            set(workload["artifacts"]),
            {"fingerprint", "quality_gate", "metric_vector", "isolation_receipt", "baseline_snapshot", "comparison"},
        )
        baseline = workload["baseline"]
        self.assertEqual((baseline["run_id"], baseline["quality_status"]), (first.name, "passed"))
        self.assertEqual(baseline["snapshot_digest"], workload["artifacts"]["baseline_snapshot"]["sha256"])
        for kind, ref in workload["artifacts"].items():
            self.assertEqual(json.loads((second / ref["path"]).read_text(encoding="utf-8"))["sha256"], ref["sha256"], kind)

    def test_no_run_time_identity_or_local_path_leaves_the_run(self) -> None:
        _, second = self.make_runs()
        text = (second / EXPORT_FILENAME).read_text(encoding="utf-8")
        for needle in ("attested_by", "executes_target_code", "snapshot_path", "/tmp/", "/home/", "consumer_contract_status"):
            self.assertNotIn(needle, text)

    def test_export_is_deterministic_and_hash_chained(self) -> None:
        _, second = self.make_runs()
        self.assertEqual(build_evaluation_export(second), self.export(second))
        hashes = json.loads((second / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(hashes["evidence_hash_chain"]["evaluation_export"]["sha256"], export_reference(self.export(second)))
        self.assertTrue(any(e["path"] == EXPORT_FILENAME for e in hashes["entries"]))

    def test_no_float_appears_anywhere_in_the_payload(self) -> None:
        _, second = self.make_runs()

        def walk(value):
            if isinstance(value, float):
                self.fail(f"float in export: {value}")
            elif isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(self.export(second))

    def test_blocked_runs_export_their_reasons(self) -> None:
        _, second = self.make_runs(first=(0.95, SLOW), second=(0.2, FAST))
        (workload,) = self.export(second)["payload"]["workloads"]
        self.assertEqual((workload["claim_status"], workload["quality_status"]), ("quality_blocked", "failed"))
        self.assertTrue(workload["blocked_reasons"])
        self.assertEqual(workload["efficiency_status"], "not_evaluated")

    def test_rejected_baselines_export_only_their_reasons(self) -> None:
        _, second = self.make_runs(first=(0.1, SLOW), second=(0.95, FAST))
        (workload,) = self.export(second)["payload"]["workloads"]
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
        forged["payload"]["workloads"][0]["claim_status"] = "permitted"
        forged["payload"]["workloads"][0]["efficiency_status"] = "improvement"
        write_json(self.path(second), reseal(forged))
        refresh_entries(second)
        self.assertBlocked(second, "differs from the run evidence")

    def test_a_changed_authority_statement_is_caught(self) -> None:
        _, second = self.make_runs()
        forged = self.load(second)
        forged["payload"]["authority"] = "Canonical truth."
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
        comparison["sha256"] = "0" * 64
        write_json(second / EVAL / "comparison.json", comparison)
        refresh_entries(second)
        self.assertFalse(validate_run_dir(second)["ok"])

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
