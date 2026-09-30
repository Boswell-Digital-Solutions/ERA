from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_review import render_eval_section
from era_core.hashing import sha256_json, sha256_path, write_json
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import make_fingerprint
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_lane import EVALUATION, write_quality, write_v2_manifest

EVAL = "evidence/efficiency/eval/eval_probe"
SLOW = ["python3", "-c", "import time; time.sleep(0.15)"]
FAST = ["python3", "-c", "pass"]


def reseal(payload: dict) -> dict:
    payload["sha256"] = sha256_json({k: v for k, v in payload.items() if k != "sha256"})
    return payload


def refresh_entries(run_dir: Path) -> None:
    """Rebuild hashes.json file entries, as a forger who edits a file would."""
    hashes = json.loads((run_dir / "hashes.json").read_text(encoding="utf-8"))
    for entry in hashes["entries"]:
        path = run_dir / entry["path"]
        if path.exists():
            entry["sha256"] = sha256_path(path)
    write_json(run_dir / "hashes.json", hashes)


class ValidationBase(unittest.TestCase):
    def make_runs(self, first=(0.95, SLOW), second=(0.95, FAST), second_evaluation=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        runs = []
        for (accuracy, command), evaluation in ((first, None), (second, second_evaluation)):
            write_quality(repo, accuracy)
            write_v2_manifest(era_root, repo.name, evaluation, command)
            runs.append(
                execute_run(
                    repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs"
                )
            )
        return runs

    def read(self, run_dir: Path, name: str) -> dict:
        return json.loads((run_dir / EVAL / name).read_text(encoding="utf-8"))

    def errors(self, run_dir: Path) -> str:
        result = validate_run_dir(run_dir)
        return "\n".join(result["errors"])

    def assertBlocked(self, run_dir: Path, needle: str) -> None:
        result = validate_run_dir(run_dir)
        self.assertFalse(result["ok"], "validation passed on tampered evidence")
        self.assertIn(needle, "\n".join(result["errors"]))


class IntactEvidenceTests(ValidationBase):
    def test_valid_run_validates_end_to_end(self) -> None:
        for run_dir in self.make_runs():
            result = validate_run_dir(run_dir)
            self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_chain_lists_every_evaluation_artifact(self) -> None:
        first, second = self.make_runs()
        chain = json.loads((second / "hashes.json").read_text(encoding="utf-8"))["evidence_hash_chain"]
        kinds = {(item["workload_id"], item["kind"]) for item in chain["evaluation_artifacts"]}
        self.assertEqual(
            kinds,
            {
                ("eval_probe", k)
                for k in ("fingerprint", "quality_gate", "metric_vector", "isolation_receipt", "baseline_snapshot", "comparison")
            },
        )


class TamperTests(ValidationBase):
    def test_edit_without_refreshing_hashes_fails(self) -> None:  # N13
        _, second = self.make_runs()
        gate = self.read(second, "quality_gate.json")
        gate["sample_count"] = 999
        write_json(second / EVAL / "quality_gate.json", gate)
        self.assertBlocked(second, "Hash mismatch")

    def test_forged_quality_gate_with_refreshed_entries_fails(self) -> None:  # N13
        _, second = self.make_runs()
        gate = self.read(second, "quality_gate.json")
        gate["sample_count"] = 999
        write_json(second / EVAL / "quality_gate.json", gate)
        refresh_entries(second)
        self.assertBlocked(second, "QualityGateArtifact sha256 mismatch")

    def test_forged_and_resealed_quality_gate_still_fails_on_references(self) -> None:
        _, second = self.make_runs()
        gate = self.read(second, "quality_gate.json")
        gate["failure_reasons"] = ["edited"]
        write_json(second / EVAL / "quality_gate.json", reseal(gate))
        refresh_entries(second)
        self.assertBlocked(second, "does not match its reference")

    def test_tampered_fingerprint_fails(self) -> None:  # N14
        _, second = self.make_runs()
        fingerprint = self.read(second, "fingerprint.json")
        fingerprint["subject_identity"]["quantization"] = "q1"
        write_json(second / EVAL / "fingerprint.json", fingerprint)
        refresh_entries(second)
        self.assertBlocked(second, "EvaluationConfigFingerprint")

    def test_stale_config_digest_fails_even_when_resealed(self) -> None:
        _, second = self.make_runs()
        fingerprint = self.read(second, "fingerprint.json")
        fingerprint["runtime_identity"] = {"interpreter": "other"}
        write_json(second / EVAL / "fingerprint.json", reseal(fingerprint))
        refresh_entries(second)
        self.assertBlocked(second, "config_digest is stale")

    def test_tampered_comparison_claim_fails(self) -> None:
        _, second = self.make_runs()
        comparison = self.read(second, "comparison.json")
        comparison["claim_status"] = "permitted"
        comparison["efficiency_status"] = "improvement"
        comparison["quality_status"] = "passed"
        write_json(second / EVAL / "comparison.json", reseal(comparison))
        refresh_entries(second)
        self.assertFalse(validate_run_dir(second)["ok"])


class MissingArtifactTests(ValidationBase):
    def test_deleted_artifacts_fail_closed(self) -> None:
        for name in ("fingerprint", "quality_gate", "metric_vector", "comparison"):
            with self.subTest(deleted=name):
                _, second = self.make_runs()
                (second / EVAL / f"{name}.json").unlink()
                refresh_entries(second)
                self.assertBlocked(second, "missing")

    def test_removed_chain_entry_fails(self) -> None:
        _, second = self.make_runs()
        hashes = json.loads((second / "hashes.json").read_text(encoding="utf-8"))
        chain = hashes["evidence_hash_chain"]
        chain["evaluation_artifacts"] = [i for i in chain["evaluation_artifacts"] if i["kind"] != "comparison"]
        write_json(second / "hashes.json", hashes)
        self.assertBlocked(second, "Evidence hash chain missing comparison")

    def test_stale_chain_hash_fails(self) -> None:
        _, second = self.make_runs()
        hashes = json.loads((second / "hashes.json").read_text(encoding="utf-8"))
        hashes["evidence_hash_chain"]["evaluation_artifacts"][0]["sha256"] = "0" * 64
        write_json(second / "hashes.json", hashes)
        self.assertBlocked(second, "stale")

    def test_chain_entry_for_unknown_artifact_fails(self) -> None:
        _, second = self.make_runs()
        hashes = json.loads((second / "hashes.json").read_text(encoding="utf-8"))
        hashes["evidence_hash_chain"]["evaluation_artifacts"].append(
            {"workload_id": "ghost", "kind": "comparison", "path": "x", "sha256": "0" * 64}
        )
        write_json(second / "hashes.json", hashes)
        self.assertBlocked(second, "missing evaluation artifact")

    def test_dropped_refs_for_a_v2_workload_fail(self) -> None:
        _, second = self.make_runs()
        bundle_path = second / "evidence/efficiency/efficiency_evidence_bundle.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle["evaluation_evidence_refs"] = {}
        write_json(bundle_path, reseal(bundle))
        refresh_entries(second)
        self.assertFalse(validate_run_dir(second)["ok"])


class BaselineReferenceTests(ValidationBase):
    def test_archiving_the_baseline_run_does_not_break_the_newer_run(self) -> None:  # operator decision 4
        first, second = self.make_runs()
        comparison = self.read(second, "comparison.json")
        self.assertEqual(comparison["baseline_run_id"], first.name)
        shutil.rmtree(first)
        result = validate_run_dir(second)
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_a_missing_snapshot_for_a_recorded_baseline_fails(self) -> None:
        _, second = self.make_runs()
        (second / EVAL / "baseline_snapshot.json").unlink()
        refresh_entries(second)
        self.assertBlocked(second, "baseline_snapshot")

    def test_a_forged_snapshot_is_caught(self) -> None:
        first, second = self.make_runs()
        snapshot = self.read(second, "baseline_snapshot.json")
        snapshot["metric_vector"]["metrics"]["median_ms"]["value"] = 1.0
        snapshot["sha256"] = "0" * 64
        write_json(second / EVAL / "baseline_snapshot.json", reseal(snapshot))
        refresh_entries(second)
        self.assertFalse(validate_run_dir(second)["ok"])

    def test_a_snapshot_that_differs_from_a_surviving_baseline_folder_fails(self) -> None:
        first, second = self.make_runs()
        vector = self.read(first, "metric_vector.json")
        vector["metrics"]["median_ms"]["value"] = 999.0
        write_json(first / EVAL / "metric_vector.json", reseal(vector))
        self.assertBlocked(second, "differs from the baseline snapshot")

    def test_reconstruction_works_from_the_snapshot_after_archiving(self) -> None:
        from era_core.eval_reconstruct import compare_to_stored

        first, second = self.make_runs()
        shutil.rmtree(first)
        result = compare_to_stored(second, "eval_probe", from_snapshot=True)
        self.assertTrue(result["match"], msg=result["differences"])
        self.assertIsNotNone(result["reconstructed"]["baseline_run_id"])

    def test_tampered_baseline_fingerprint_fails(self) -> None:
        first, second = self.make_runs()
        fingerprint = self.read(first, "fingerprint.json")
        fingerprint["evaluation_identity"]["dataset_or_fixture_hash"] = "swapped"
        write_json(first / EVAL / "fingerprint.json", fingerprint)
        self.assertBlocked(second, "baseline run")

    def test_baseline_that_no_longer_qualifies_fails(self) -> None:
        first, second = self.make_runs()
        gate = self.read(first, "quality_gate.json")
        gate.update(gate_status="failed", failure_reasons=["forged"])
        gate["metric_results"] = {"accuracy": 0.1}
        write_json(first / EVAL / "quality_gate.json", reseal(gate))
        self.assertBlocked(second, "baseline run")

    def test_baseline_status_edit_in_baseline_artifact_fails(self) -> None:
        _, second = self.make_runs()
        path = second / "evidence/efficiency/baseline_artifact.json"
        baseline = json.loads(path.read_text(encoding="utf-8"))
        baseline["comparisons"][0]["comparison_status"] = "improvement"
        baseline["comparisons"][0]["claim_status"] = "quality_blocked"
        write_json(path, reseal(baseline))
        refresh_entries(second)
        self.assertBlocked(second, "does not match")


class ReviewRenderingTests(ValidationBase):
    def review(self, run_dir: Path) -> str:
        return (run_dir / "review.md").read_text(encoding="utf-8")

    def test_review_shows_gating_context(self) -> None:
        first, second = self.make_runs()
        review = self.review(second)
        comparison = self.read(second, "comparison.json")
        fingerprint = self.read(second, "fingerprint.json")
        for text in (
            "### Quality-Gated Evaluation",
            f"candidate fingerprint: `{fingerprint['fingerprint_id']}`",
            "quality gate status: `passed`",
            f"baseline run: `{first.name}`",
            f"baseline fingerprint: `{comparison['baseline_fingerprint_id']}`",
            f"comparability: `{comparison['comparability_status']}`",
            "stability: candidate",
            "| median_ms (primary) | lower_is_better |",
            self.read(second, "comparison.json")["sha256"],
        ):
            self.assertIn(text, review)

    def test_blocked_faster_candidate_never_renders_improvement(self) -> None:  # N01
        _, second = self.make_runs(first=(0.95, SLOW), second=(0.2, FAST))
        review = self.review(second)
        self.assertIn("claim status: `quality_blocked`", review)
        self.assertIn("no improvement or regression claim was made", review)
        self.assertIn("quality reason:", review)
        self.assertNotIn("improvement`", review)
        self.assertNotIn("| improvement", review)

    def test_incomparable_run_shows_blocked_reason_and_rejections(self) -> None:
        changed = copy.deepcopy(EVALUATION)
        changed["evaluation_identity"]["dataset_or_fixture_hash"] = "other"
        _, second = self.make_runs(second_evaluation=changed)
        review = self.review(second)
        self.assertIn("comparability: `incomparable`", review)
        self.assertIn("blocked reason:", review)
        self.assertIn("reason=`fingerprint_incomparable`", review)

    def test_quality_failed_prior_is_listed_as_rejected(self) -> None:  # N21 end to end
        first, second = self.make_runs(first=(0.1, SLOW), second=(0.95, FAST))
        review = self.review(second)
        self.assertIn("claim status: `no_baseline`", review)
        self.assertIn(f"`{first.name}` reason=`quality_failed`", review)


class RenderUnitTests(unittest.TestCase):
    def test_permitted_claim_states_why(self) -> None:
        refs = {"w": {"quality_status": "passed", "problems": []}}
        comparison = {
            "claim_status": "permitted",
            "efficiency_status": "improvement",
            "comparability_status": "comparable",
            "baseline_run_id": "r0",
            "baseline_fingerprint_id": "fp0",
            "blocked_reasons": [],
            "baseline_rejections": [],
            "metric_deltas": {
                "median_ms": {
                    "direction": "lower_is_better",
                    "candidate": 50,
                    "baseline": 100,
                    "delta": -50,
                    "delta_pct": -50.0,
                    "baseline_stability": "stable",
                }
            },
        }
        found = {"w": {"comparison": comparison, "fingerprint": make_fingerprint(), "quality_gate": {"gate_status": "passed"}}}
        text = "\n".join(render_eval_section(refs, found))
        self.assertIn("efficiency outcome: `improvement`, reported because quality passed", text)

    def test_missing_comparison_renders_evidence_blocked(self) -> None:
        text = "\n".join(render_eval_section({"w": {"quality_status": "invalid", "problems": ["p"]}}, {"w": {}}))
        self.assertIn("evidence_blocked", text)
        self.assertIn("evidence problem: p", text)
        self.assertNotIn("improvement", text.replace("no improvement or regression claim", ""))

    def test_no_refs_renders_nothing(self) -> None:
        self.assertEqual(render_eval_section({}, {}), [])


if __name__ == "__main__":
    unittest.main()
