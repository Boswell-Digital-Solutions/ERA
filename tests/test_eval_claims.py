from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_claims import (
    build_comparison_artifact,
    decide_claim,
    load_prior_evidence,
    select_eligible_baseline,
)
from era_core.eval_comparability import DEFAULT_REQUIRED_DIMENSIONS
from era_core.eval_contracts import (
    build_metric_vector,
    build_quality_gate_artifact,
    validate_quality_efficiency_comparison,
)
from tests.fixtures.eval.factories import make_fingerprint
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_lane import EVALUATION, write_quality, write_v2_manifest

FLOORS = {"accuracy": {"min": 0.9}}
THRESHOLDS = {"regression_threshold_pct": 10.0, "improvement_threshold_pct": 10.0}


def evidence(run_id="run-c", median=100.0, accuracy=0.95, variance="stable", direction="lower_is_better", **fp):
    fingerprint = make_fingerprint(run_id=run_id, **fp)
    gate = build_quality_gate_artifact(
        fingerprint=fingerprint,
        metric_results={"accuracy": accuracy},
        quality_floors=FLOORS,
        sample_count=10,
        raw_evidence_refs=["r"],
    )
    vector = build_metric_vector(
        fingerprint=fingerprint,
        metrics={"median_ms": {"value": median, "unit": "ms", "direction": direction}},
        sample_count=3,
        variance_or_uncertainty={"variance_classification": variance},
        measurement_scope="wall_clock",
        raw_evidence_refs=["r"],
    )
    return {
        "workload_id": fingerprint["workload_id"],
        "fingerprint": fingerprint,
        "quality_gate": gate,
        "metric_vector": vector,
        "quality_status": gate["gate_status"],
        "problems": [],
    }


def as_prior(item):
    return {
        "run_id": item["fingerprint"]["run_id"],
        "fingerprint": item["fingerprint"],
        "quality_gate": item["quality_gate"],
        "metric_vector": item["metric_vector"],
    }


def decide(candidate, priors, required=DEFAULT_REQUIRED_DIMENSIONS):
    selection = select_eligible_baseline(candidate["fingerprint"], [as_prior(p) for p in priors], tuple(required))
    decision = decide_claim(candidate=candidate, selection=selection, **THRESHOLDS)
    return decision, selection


class DecisionTableTests(unittest.TestCase):
    def test_faster_stable_comparable_is_improvement(self) -> None:  # P01
        decision, _ = decide(evidence(median=50), [evidence("run-b", 100)])
        self.assertEqual((decision["efficiency_status"], decision["claim_status"]), ("improvement", "permitted"))
        self.assertEqual(decision["metric_deltas"]["median_ms"]["delta_pct"], -50.0)

    def test_slower_is_regression(self) -> None:  # P02
        decision, _ = decide(evidence(median=150), [evidence("run-b", 100)])
        self.assertEqual((decision["efficiency_status"], decision["claim_status"]), ("regression", "permitted"))

    def test_inside_threshold_is_within_range(self) -> None:  # P03
        decision, _ = decide(evidence(median=105), [evidence("run-b", 100)])
        self.assertEqual((decision["efficiency_status"], decision["claim_status"]), ("within_range", "permitted"))

    def test_higher_is_better_flips_the_sign(self) -> None:
        decision, _ = decide(
            evidence(median=150, direction="higher_is_better"),
            [evidence("run-b", 100, direction="higher_is_better")],
        )
        self.assertEqual(decision["efficiency_status"], "improvement")

    def test_failed_quality_blocks_a_faster_candidate(self) -> None:  # N01
        decision, _ = decide(evidence(median=10, accuracy=0.5), [evidence("run-b", 100)])
        self.assertEqual(decision["claim_status"], "quality_blocked")
        self.assertEqual(decision["efficiency_status"], "not_evaluated")

    def test_unproven_quality_blocks(self) -> None:  # N02
        candidate = evidence(median=10)
        candidate["quality_status"] = "unproven"
        candidate["quality_gate"]["failure_reasons"] = ["no results"]
        decision, _ = decide(candidate, [evidence("run-b", 100)])
        self.assertEqual(decision["claim_status"], "quality_unproven")

    def test_invalid_quality_is_evidence_blocked(self) -> None:
        candidate = evidence(median=10)
        candidate["quality_status"] = "invalid"
        candidate["problems"] = ["bad"]
        self.assertEqual(decide(candidate, [evidence("run-b", 100)])[0]["claim_status"], "evidence_blocked")

    def test_quality_for_another_fingerprint_is_evidence_blocked(self) -> None:  # N11
        candidate = evidence(median=10)
        candidate["quality_gate"] = evidence("run-z", 10)["quality_gate"]
        self.assertEqual(decide(candidate, [evidence("run-b", 100)])[0]["claim_status"], "evidence_blocked")

    def test_config_mismatch_is_incomparable_not_improvement(self) -> None:  # N03-N06
        for key, value in {
            "subject_identity.model_revision": "rev2",
            "subject_identity.quantization": "q4",
            "evaluation_identity.dataset_or_fixture_hash": "d2",
            "evaluation_identity.quality_floor_policy_id": "floor-2",
        }.items():
            with self.subTest(key=key):
                required = DEFAULT_REQUIRED_DIMENSIONS + ("subject.model_revision", "subject.quantization")
                decision, _ = decide(evidence(median=10, **{key: value}), [evidence("run-b", 100)], required)
                self.assertEqual(decision["claim_status"], "incomparable")
                self.assertEqual(decision["comparability_status"], "incomparable")

    def test_unstable_timing_gives_no_claim(self) -> None:  # N10
        for candidate, prior in (
            (evidence(median=10, variance="unstable"), evidence("run-b", 100)),
            (evidence(median=10), evidence("run-b", 100, variance="single_sample")),
        ):
            decision, _ = decide(candidate, [prior])
            self.assertEqual((decision["efficiency_status"], decision["claim_status"]), ("unstable", "no_claim_unstable"))

    def test_no_prior_run_is_no_baseline(self) -> None:
        decision, _ = decide(evidence(median=10), [])
        self.assertEqual(decision["claim_status"], "no_baseline")

    def test_comparable_prior_that_failed_quality_is_rejected_as_baseline(self) -> None:  # N21
        decision, selection = decide(evidence(median=10), [evidence("run-b", 100, accuracy=0.1)])
        self.assertEqual(decision["claim_status"], "no_baseline")
        self.assertEqual(decision["efficiency_status"], "not_evaluated")
        self.assertEqual(decision["metric_deltas"], {})
        self.assertEqual([(r["run_id"], r["reason"]) for r in selection["rejected"]], [("run-b", "quality_failed")])
        self.assertIn("not a fair baseline", " ".join(decision["blocked_reasons"]))

    def test_newest_prior_quality_failed_selects_older_qualified_run(self) -> None:  # N22
        older = evidence("run-1", 200)
        newer_failed = evidence("run-2", 100, accuracy=0.1)
        newest_failed = evidence("run-3", 90, accuracy=0.2)
        decision, selection = decide(evidence(median=50), [older, newer_failed, newest_failed])
        self.assertEqual(selection["baseline"]["run_id"], "run-1")
        self.assertEqual(decision["claim_status"], "permitted")
        self.assertEqual(decision["metric_deltas"]["median_ms"]["baseline"], 200)
        self.assertEqual(sorted(r["run_id"] for r in selection["rejected"]), ["run-2", "run-3"])

    def test_unproven_prior_is_rejected_with_its_own_reason(self) -> None:
        prior = evidence("run-b", 100)
        gate = build_quality_gate_artifact(
            fingerprint=prior["fingerprint"],
            metric_results={},
            quality_floors=FLOORS,
            sample_count=10,
            raw_evidence_refs=["r"],
        )
        prior["quality_gate"] = gate
        decision, selection = decide(evidence(median=10), [prior])
        self.assertEqual(selection["rejected"][0]["reason"], "quality_unproven")
        self.assertEqual(decision["claim_status"], "no_baseline")

    def test_quality_failed_and_incomparable_mix_is_no_baseline(self) -> None:
        failed = evidence("run-1", 100, accuracy=0.1)
        other_data = evidence("run-2", 100, **{"evaluation_identity.dataset_or_fixture_hash": "d2"})
        decision, selection = decide(evidence(median=10), [failed, other_data])
        self.assertEqual(decision["claim_status"], "no_baseline")
        self.assertEqual(sorted(r["reason"] for r in selection["rejected"]), ["fingerprint_incomparable", "quality_failed"])

    def test_incomparable_prior_that_also_failed_quality_is_incomparable_not_quality(self) -> None:
        prior = evidence("run-b", 100, accuracy=0.1, **{"evaluation_identity.dataset_or_fixture_hash": "d2"})
        decision, selection = decide(evidence(median=10), [prior])
        self.assertEqual(selection["rejected"][0]["reason"], "fingerprint_incomparable")
        self.assertEqual(decision["claim_status"], "incomparable")

    def test_rejection_ledger_is_in_the_comparison_artifact(self) -> None:
        candidate = evidence(median=10)
        decision, selection = decide(candidate, [evidence("run-b", 100, accuracy=0.1)])
        artifact = build_comparison_artifact(
            run_id="run-c", workload_id="fixture_workload", candidate=candidate, selection=selection, decision=decision
        )
        self.assertEqual(artifact["baseline_rejections"][0]["reason"], "quality_failed")
        self.assertEqual(validate_quality_efficiency_comparison(artifact), [])
        artifact["baseline_rejections"][0]["reason"] = "vibes"
        self.assertTrue(validate_quality_efficiency_comparison(artifact))

    def test_tampered_prior_is_not_a_baseline(self) -> None:
        prior = evidence("run-b", 100)
        prior["metric_vector"]["metrics"]["median_ms"]["value"] = 1.0
        self.assertEqual(decide(evidence(median=10), [prior])[0]["claim_status"], "evidence_blocked")

    def test_missing_or_informational_direction_is_evidence_blocked(self) -> None:  # N16
        decision, _ = decide(
            evidence(median=10, direction="informational_only"),
            [evidence("run-b", 100, direction="informational_only")],
        )
        self.assertEqual(decision["claim_status"], "evidence_blocked")

    def test_direction_disagreement_is_evidence_blocked(self) -> None:
        decision, _ = decide(evidence(median=10), [evidence("run-b", 100, direction="higher_is_better")])
        self.assertEqual(decision["claim_status"], "evidence_blocked")

    def test_baseline_choice_skips_incomparable_and_takes_latest_comparable(self) -> None:  # N15
        older = evidence("run-1", 200)
        other = evidence("run-2", 100, **{"evaluation_identity.dataset_or_fixture_hash": "d2"})
        decision, selection = decide(evidence(median=50), [older, other])
        self.assertEqual(selection["baseline"]["run_id"], "run-1")
        self.assertEqual(decision["metric_deltas"]["median_ms"]["baseline"], 200)

    def test_every_decision_builds_a_valid_comparison(self) -> None:
        cases = [
            (evidence(median=50), [evidence("run-b", 100)]),
            (evidence(median=150), [evidence("run-b", 100)]),
            (evidence(median=10, accuracy=0.5), [evidence("run-b", 100)]),
            (evidence(median=10, variance="unstable"), [evidence("run-b", 100)]),
            (evidence(median=10), []),
            (evidence(median=10, **{"evaluation_identity.dataset_or_fixture_hash": "d2"}), [evidence("run-b", 100)]),
            (evidence(median=10), [evidence("run-b", 100, accuracy=0.1)]),
        ]
        for candidate, priors in cases:
            decision, selection = decide(candidate, priors)
            artifact = build_comparison_artifact(
                run_id="run-c", workload_id="fixture_workload", candidate=candidate, selection=selection, decision=decision
            )
            self.assertEqual(validate_quality_efficiency_comparison(artifact), [], decision["claim_status"])


class LoadPriorTests(unittest.TestCase):
    def test_missing_dir_and_self_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(load_prior_evidence(root / "none", "r", "w", "w"), [])
            (root / "r" / "evidence" / "efficiency" / "eval" / "w").mkdir(parents=True)
            self.assertEqual(load_prior_evidence(root, "r", "w", "w"), [])
            broken = root / "old" / "evidence" / "efficiency" / "eval" / "w"
            broken.mkdir(parents=True)
            (broken / "fingerprint.json").write_text("not json", encoding="utf-8")
            (prior,) = load_prior_evidence(root, "r", "w", "w")
            self.assertIsNone(prior["fingerprint"])


class EndToEndTests(unittest.TestCase):
    def run_pair(self, first_accuracy, second_accuracy, second_evaluation=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        runs = []
        for accuracy, evaluation in ((first_accuracy, None), (second_accuracy, second_evaluation)):
            write_quality(repo, accuracy)
            write_v2_manifest(era_root, repo.name, evaluation)
            runs.append(
                execute_run(
                    repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs"
                )
            )
        efficiency = runs[1] / "evidence" / "efficiency"
        comparison = json.loads((efficiency / "eval" / "eval_probe" / "comparison.json").read_text(encoding="utf-8"))
        baseline = json.loads((efficiency / "baseline_artifact.json").read_text(encoding="utf-8"))
        return runs, comparison, baseline["comparisons"][0], (runs[1] / "review.md").read_text(encoding="utf-8")

    def test_first_run_has_no_baseline_then_second_run_compares(self) -> None:
        runs, comparison, entry, _ = self.run_pair(0.95, 0.95)
        first = json.loads(
            (runs[0] / "evidence/efficiency/eval/eval_probe/comparison.json").read_text(encoding="utf-8")
        )
        self.assertEqual(first["claim_status"], "no_baseline")
        self.assertEqual(validate_quality_efficiency_comparison(comparison), [])
        self.assertEqual(comparison["baseline_run_id"], runs[0].name)
        self.assertIn(comparison["claim_status"], {"permitted", "no_claim_unstable"})
        self.assertEqual(entry["baseline_run_id"], runs[0].name)

    def test_changed_dataset_makes_second_run_incomparable(self) -> None:
        changed = copy.deepcopy(EVALUATION)
        changed["evaluation_identity"]["dataset_or_fixture_hash"] = "fixture-hash-2"
        _, comparison, entry, review = self.run_pair(0.95, 0.95, changed)
        self.assertEqual(comparison["claim_status"], "incomparable")
        self.assertEqual(entry["comparison_status"], "incomparable")
        self.assertIn("Classification: `incomparable`", review)

    def test_failed_quality_in_second_run_is_quality_blocked(self) -> None:
        _, comparison, entry, review = self.run_pair(0.95, 0.4)
        self.assertEqual(comparison["claim_status"], "quality_blocked")
        self.assertEqual(entry["comparison_status"], "quality_blocked")
        self.assertIn("Classification: `quality_blocked`", review)

    def test_a_baseline_that_failed_quality_is_not_used(self) -> None:
        runs, comparison, _, _ = self.run_pair(0.4, 0.95)
        self.assertIsNone(comparison["baseline_run_id"])
        self.assertEqual(comparison["claim_status"], "no_baseline")
        self.assertEqual(
            [(r["run_id"], r["reason"]) for r in comparison["baseline_rejections"]], [(runs[0].name, "quality_failed")]
        )


if __name__ == "__main__":
    unittest.main()
