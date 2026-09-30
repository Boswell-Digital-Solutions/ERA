from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_lane import apply_quality_gate, validate_eval_policy
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import make_fingerprint
from tests.test_artifact_generation import init_git_repo

EVALUATION = {
    "subject_kind": "repository_command",
    "runtime_identity": {"interpreter": "python3"},
    "evaluation_identity": {
        "suite_id": "fixture-suite",
        "suite_version": "1",
        "dataset_or_fixture_hash": "fixture-hash-1",
        "scorer_id": "fixture-scorer",
        "scorer_version": "1",
        "harness_id": "era-fixture",
        "harness_version": "1",
        "split_or_holdout_class": "public_fixture",
        "quality_floor_policy_id": "fixture-floor-1",
    },
    "execution_identity": {"hardware_fingerprint": "fixture-host", "concurrency": 1, "batch_size": 1},
    "quality_gate_policy": {
        "quality_floors": {"accuracy": {"min": 0.9}},
        "quality_results_path": "quality/results.json",
    },
    "metrics": {"median_ms": "lower_is_better"},
}


def write_v2_manifest(
    era_root: Path, repo_name: str, evaluation: dict | None = None, command: list[str] | None = None,
    threshold_pct: float = 500.0,
) -> None:
    manifests = era_root / "config" / "workload_manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / f"{repo_name.lower()}.json").write_text(
        json.dumps(
            {
                "schema_version": "EfficiencyWorkloadManifest.v2",
                "repo_id": repo_name,
                "workloads": [
                    {
                        "workload_id": "eval_probe",
                        "label": "eval probe",
                        "category": "runtime_benchmark",
                        "command": command or ["python3", "-c", "import time; time.sleep(0.01)"],
                        "cwd_subpath": ".",
                        "runner": "internal_timer",
                        "iterations": 3,
                        "regression_threshold_pct": threshold_pct,
                        "improvement_threshold_pct": threshold_pct,
                        "evaluation": evaluation if evaluation is not None else copy.deepcopy(EVALUATION),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def write_quality(repo: Path, accuracy: float | None, samples: int = 20) -> None:
    (repo / "quality").mkdir(exist_ok=True)
    results = {} if accuracy is None else {"accuracy": accuracy}
    (repo / "quality" / "results.json").write_text(
        json.dumps({"metric_results": results, "sample_count": samples}), encoding="utf-8"
    )


class EvalLaneRunTests(unittest.TestCase):
    def run_once(self, *, accuracy, evaluation=None, write_results=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        if write_results:
            write_quality(repo, accuracy)
        write_v2_manifest(era_root, repo.name, evaluation)
        run_dir = execute_run(
            repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs"
        )
        efficiency = run_dir / "evidence" / "efficiency"
        baseline = json.loads((efficiency / "baseline_artifact.json").read_text(encoding="utf-8"))
        review = (run_dir / "review.md").read_text(encoding="utf-8")
        return run_dir, efficiency, baseline["comparisons"][0], review

    def test_passing_quality_writes_bound_artifacts(self) -> None:
        run_dir, efficiency, comparison, _ = self.run_once(accuracy=0.95)
        directory = efficiency / "eval" / "eval_probe"
        fingerprint = json.loads((directory / "fingerprint.json").read_text(encoding="utf-8"))
        gate = json.loads((directory / "quality_gate.json").read_text(encoding="utf-8"))
        vector = json.loads((directory / "metric_vector.json").read_text(encoding="utf-8"))
        self.assertEqual(gate["gate_status"], "passed")
        self.assertEqual(gate["config_fingerprint_id"], fingerprint["fingerprint_id"])
        self.assertEqual(gate["config_fingerprint_sha256"], fingerprint["sha256"])
        self.assertEqual(vector["config_fingerprint_id"], fingerprint["fingerprint_id"])
        self.assertEqual(comparison["quality_status"], "passed")
        self.assertNotIn(comparison["comparison_status"], {"quality_blocked", "quality_unproven", "evidence_blocked"})
        result = validate_run_dir(run_dir)
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_sandbox_posture_is_part_of_execution_identity(self) -> None:
        _, efficiency, _, _ = self.run_once(accuracy=0.95)
        fingerprint = json.loads((efficiency / "eval" / "eval_probe" / "fingerprint.json").read_text(encoding="utf-8"))
        identity = fingerprint["execution_identity"]
        for key in ("sandbox", "sandbox_backend", "network", "target_filesystem"):
            self.assertIn(key, identity)
        self.assertEqual(identity["hardware_fingerprint"], "fixture-host")

    def test_failed_quality_blocks_and_is_not_a_regression(self) -> None:  # N01
        run_dir, _, comparison, review = self.run_once(accuracy=0.5)
        self.assertEqual(comparison["comparison_status"], "quality_blocked")
        self.assertEqual(comparison["quality_status"], "failed")
        self.assertTrue(comparison["blocked_reasons"])
        self.assertIn("Classification: `quality_blocked`", review)
        findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual([f for f in findings["era_findings"] if f["lane"] == "efficiency"], [])

    def test_missing_quality_evidence_is_unproven(self) -> None:  # N02
        _, _, comparison, review = self.run_once(accuracy=None, write_results=False)
        self.assertEqual(comparison["comparison_status"], "quality_unproven")
        self.assertIn("Classification: `quality_unproven`", review)

    def test_empty_results_are_unproven_not_passed(self) -> None:
        _, _, comparison, _ = self.run_once(accuracy=None)
        self.assertEqual(comparison["comparison_status"], "quality_unproven")

    def test_misdeclared_policy_is_evidence_blocked(self) -> None:
        bad = copy.deepcopy(EVALUATION)
        del bad["evaluation_identity"]["scorer_version"]
        run_dir, _, comparison, review = self.run_once(accuracy=0.95, evaluation=bad)
        self.assertEqual(comparison["comparison_status"], "evidence_blocked")
        self.assertIn("scorer_version", " ".join(comparison["blocked_reasons"]))
        self.assertIn("Classification: `blocked_by_missing_evidence`", review)

    def test_results_path_escape_is_not_read(self) -> None:
        escaping = copy.deepcopy(EVALUATION)
        escaping["quality_gate_policy"]["quality_results_path"] = "../outside.json"
        _, _, comparison, _ = self.run_once(accuracy=0.95, evaluation=escaping)
        self.assertEqual(comparison["comparison_status"], "quality_unproven")
        self.assertIn("escapes", " ".join(comparison["blocked_reasons"]))

    def test_legacy_v1_workload_is_unchanged(self) -> None:  # P04
        from tests.test_efficiency import write_efficiency_manifest

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            era_root, repo = root / "era", root / "repo"
            era_root.mkdir()
            repo.mkdir()
            init_git_repo(repo)
            write_efficiency_manifest(era_root, repo.name, ["python3", "-c", "pass"])
            run_dir = execute_run(
                repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs"
            )
            baseline = json.loads((run_dir / "evidence/efficiency/baseline_artifact.json").read_text(encoding="utf-8"))
            self.assertNotIn("evaluation", baseline["comparisons"][0])
            self.assertFalse((run_dir / "evidence/efficiency/eval").exists() and any((run_dir / "evidence/efficiency/eval").iterdir()))


class ApplyQualityGateTests(unittest.TestCase):
    """GATE-03: a faster candidate never earns `improvement` without a passed gate."""

    @staticmethod
    def artifact(status: str) -> dict:
        return {
            "comparisons": [
                {"workload_id": "w", "comparison_status": status, "delta_pct": -80.0},
                {"workload_id": "legacy", "comparison_status": status, "delta_pct": -80.0},
            ]
        }

    @staticmethod
    def evidence(quality_status: str) -> dict:
        return {
            "w": {
                "quality_status": quality_status,
                "fingerprint": make_fingerprint(),
                "quality_gate": {"failure_reasons": ["reason"]},
                "problems": ["problem"],
            }
        }

    def test_faster_candidate_is_blocked_unless_quality_passed(self) -> None:
        expected = {"failed": "quality_blocked", "unproven": "quality_unproven", "invalid": "evidence_blocked"}
        for quality, blocked in expected.items():
            with self.subTest(quality=quality):
                result = apply_quality_gate(self.artifact("improvement"), self.evidence(quality))
                self.assertEqual(result["comparisons"][0]["comparison_status"], blocked)
                self.assertEqual(result["comparisons"][0]["timing_comparison_status"], "improvement")

    def test_regression_is_also_replaced_by_quality_failure(self) -> None:
        result = apply_quality_gate(self.artifact("regression"), self.evidence("failed"))
        self.assertEqual(result["comparisons"][0]["comparison_status"], "quality_blocked")

    def test_passed_quality_keeps_timing_status_and_legacy_is_untouched(self) -> None:
        result = apply_quality_gate(self.artifact("improvement"), self.evidence("passed"))
        self.assertEqual(result["comparisons"][0]["comparison_status"], "improvement")
        self.assertEqual(result["comparisons"][1]["comparison_status"], "improvement")
        self.assertNotIn("evaluation", result["comparisons"][1])

    def test_artifact_is_resealed(self) -> None:
        from era_core.hashing import sha256_json

        result = apply_quality_gate(self.artifact("improvement"), self.evidence("failed"))
        self.assertEqual(result["sha256"], sha256_json({k: v for k, v in result.items() if k != "sha256"}))


class PolicyValidationTests(unittest.TestCase):
    def test_valid_policy(self) -> None:
        self.assertEqual(validate_eval_policy(copy.deepcopy(EVALUATION)), [])

    def test_bad_policies(self) -> None:
        cases = {
            "subject_kind": lambda p: p.update(subject_kind="oracle"),
            "quality_floors": lambda p: p["quality_gate_policy"].update(quality_floors={}),
            "quality_results_path": lambda p: p["quality_gate_policy"].pop("quality_results_path"),
            "direction": lambda p: p["metrics"].update(median_ms="faster"),
            "metrics": lambda p: p.update(metrics={}),
            "dimension": lambda p: p.update(required_comparison_dimensions=["vibes"]),
            "non_binding": lambda p: p.update(non_binding_dimensions=["nonsense"]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                policy = copy.deepcopy(EVALUATION)
                mutate(policy)
                self.assertTrue(validate_eval_policy(policy))


if __name__ == "__main__":
    unittest.main()
