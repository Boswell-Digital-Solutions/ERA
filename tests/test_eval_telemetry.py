from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_claims import decide_claim, select_eligible_baseline
from era_core.eval_comparability import DEFAULT_REQUIRED_DIMENSIONS
from era_core.eval_contracts import build_metric_vector, build_quality_gate_artifact
from era_core.eval_lane import required_dimensions, validate_eval_policy
from era_core.eval_telemetry import (
    percentile,
    read_telemetry,
    summarize_telemetry,
    validate_telemetry_policy,
    variance_class,
)
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import FIXED_TIME, make_fingerprint
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_lane import EVALUATION, write_quality, write_v2_manifest

DIRECTIONS = {
    "ttft_ms": "lower_is_better",
    "output_tokens_per_second": "higher_is_better",
    "vram_mb": "lower_is_better",
    "output_tokens": "informational_only",
}
POLICY = {"telemetry_results_path": "telemetry/results.json", "percentile_metrics": ["ttft_ms"]}


def payload(**samples):
    return {"schema_version": "InferenceTelemetry.v1", "measurement_scope": "local_engine_client", "samples": samples}


class SummaryTests(unittest.TestCase):
    def test_nearest_rank_percentiles(self) -> None:
        values = list(range(1, 101))
        self.assertEqual([percentile(values, p) for p in (50, 95, 99)], [50, 95, 99])
        self.assertEqual(percentile([7.0], 99), 7.0)

    def test_variance_classes(self) -> None:
        self.assertEqual(variance_class([100, 101, 100]), "stable")
        self.assertEqual(variance_class([100, 110, 100]), "moderate_variance")
        self.assertEqual(variance_class([10, 100, 10]), "unstable")
        self.assertEqual(variance_class([5]), "single_sample")
        self.assertEqual(variance_class([0, 0]), "stable")

    def test_medians_directions_and_units(self) -> None:
        result = summarize_telemetry(
            payload(ttft_ms=[10, 20, 30], output_tokens_per_second=[50, 52, 51], vram_mb=[4000, 4000], output_tokens=[64, 64]),
            DIRECTIONS,
            {},
        )
        metrics = result["metrics"]
        self.assertEqual(metrics["ttft_ms"]["value"], 20)
        self.assertEqual(metrics["ttft_ms"]["direction"], "lower_is_better")
        self.assertEqual(metrics["output_tokens_per_second"]["direction"], "higher_is_better")
        self.assertEqual(metrics["vram_mb"]["unit"], "MB")
        self.assertEqual(metrics["output_tokens"]["direction"], "informational_only")
        self.assertEqual(result["problems"], [])

    def test_percentiles_appear_only_with_enough_samples(self) -> None:
        few = summarize_telemetry(payload(ttft_ms=list(range(1, 11))), {"ttft_ms": "lower_is_better"}, POLICY)
        self.assertIn("ttft_ms_p50", few["metrics"])
        self.assertNotIn("ttft_ms_p95", few["metrics"])
        self.assertNotIn("ttft_ms_p99", few["metrics"])
        self.assertTrue(any("ttft_ms_p95 omitted: 10 samples" in n for n in few["notes"]))
        many = summarize_telemetry(payload(ttft_ms=list(range(1, 201))), {"ttft_ms": "lower_is_better"}, POLICY)
        self.assertEqual(many["metrics"]["ttft_ms_p95"]["value"], 190)
        self.assertEqual(many["metrics"]["ttft_ms_p99"]["value"], 198)
        self.assertEqual(many["metrics"]["ttft_ms_p99"]["direction"], "lower_is_better")

    def test_custom_percentile_minimums(self) -> None:
        result = summarize_telemetry(
            payload(ttft_ms=list(range(1, 6))),
            {"ttft_ms": "lower_is_better"},
            {**POLICY, "p95_min_samples": 5, "p99_min_samples": 5},
        )
        self.assertIn("ttft_ms_p99", result["metrics"])

    def test_percentile_metrics_are_opt_in(self) -> None:
        result = summarize_telemetry(payload(ttft_ms=list(range(1, 300))), {"ttft_ms": "lower_is_better"}, {})
        self.assertEqual(list(result["metrics"]), ["ttft_ms"])

    def test_undeclared_metric_is_ignored_and_missing_or_bad_samples_are_named(self) -> None:
        result = summarize_telemetry(
            payload(ttft_ms=[1, 2], vram_mb=[True, 2], tpot_ms=[5]), {"ttft_ms": "lower_is_better", "vram_mb": "lower_is_better", "itl_ms": "lower_is_better"}, {}
        )
        self.assertEqual(list(result["metrics"]), ["ttft_ms"])
        self.assertEqual(len(result["problems"]), 2)
        self.assertNotIn("tpot_ms", result["metrics"])

    def test_non_finite_and_negative_samples_are_rejected(self) -> None:
        for bad in ([float("nan")], [float("inf")], [-1.0], []):
            result = summarize_telemetry(payload(ttft_ms=bad), {"ttft_ms": "lower_is_better"}, {})
            self.assertEqual(result["metrics"], {}, bad)
            self.assertTrue(result["problems"])

    def test_no_combined_score_is_produced(self) -> None:
        result = summarize_telemetry(payload(ttft_ms=[1, 2], vram_mb=[3, 4]), DIRECTIONS, {})
        self.assertFalse({"score", "efficiency_score", "combined"} & set(result))
        self.assertFalse(any("score" in name for name in result["metrics"]))


class ReadAndPolicyTests(unittest.TestCase):
    def test_read_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "telemetry").mkdir()
            good = root / "telemetry" / "results.json"
            good.write_text(json.dumps(payload(ttft_ms=[1])), encoding="utf-8")
            data, digest, problems = read_telemetry(root, ".", "telemetry/results.json")
            self.assertEqual((problems, bool(digest)), ([], True))
            self.assertIsNotNone(data)
            self.assertIn("escapes", read_telemetry(root, ".", "../x.json")[2][0])
            self.assertIn("does not exist", read_telemetry(root, ".", "telemetry/none.json")[2][0])
            good.write_text("nope", encoding="utf-8")
            self.assertIn("not valid JSON", read_telemetry(root, ".", "telemetry/results.json")[2][0])
            good.write_text(json.dumps({"schema_version": "Other.v1"}), encoding="utf-8")
            self.assertIn("is not InferenceTelemetry.v1", read_telemetry(root, ".", "telemetry/results.json")[2][0])
            good.write_text(json.dumps({"schema_version": "InferenceTelemetry.v1", "samples": {}}), encoding="utf-8")
            self.assertIn("needs samples", read_telemetry(root, ".", "telemetry/results.json")[2][0])

    def test_policy_validation(self) -> None:
        self.assertEqual(validate_telemetry_policy(POLICY), [])
        self.assertTrue(validate_telemetry_policy({}))
        self.assertTrue(validate_telemetry_policy({**POLICY, "percentile_metrics": ["vibes"]}))
        self.assertTrue(validate_telemetry_policy({**POLICY, "p95_min_samples": 0}))
        self.assertTrue(validate_telemetry_policy("x"))

    def test_eval_policy_primary_metric_rules(self) -> None:
        base = copy.deepcopy(EVALUATION)
        base["metrics"] = {"median_ms": "lower_is_better", "ttft_ms": "lower_is_better", "output_tokens": "informational_only"}
        base["telemetry_policy"] = POLICY
        self.assertEqual(validate_eval_policy(base), [])
        self.assertTrue(validate_eval_policy({**base, "primary_metric": "ghost"}))
        self.assertTrue(validate_eval_policy({**base, "primary_metric": "output_tokens"}))
        self.assertEqual(validate_eval_policy({**base, "primary_metric": "ttft_ms"}), [])

    def test_telemetry_makes_hardware_concurrency_and_batch_required(self) -> None:
        plain = required_dimensions(copy.deepcopy(EVALUATION))
        with_telemetry = required_dimensions({**EVALUATION, "telemetry_policy": POLICY})
        self.assertNotIn("execution.concurrency", plain)
        for name in ("execution.hardware_fingerprint", "execution.concurrency", "execution.batch_size"):
            self.assertIn(name, with_telemetry)


def vec_evidence(run_id, metrics, per_metric=None, accuracy=0.95, **fp):
    fingerprint = make_fingerprint(run_id=run_id, **fp)
    gate = build_quality_gate_artifact(
        fingerprint=fingerprint,
        metric_results={"accuracy": accuracy},
        quality_floors={"accuracy": {"min": 0.9}},
        sample_count=10,
        raw_evidence_refs=["r"],
    )
    vector = build_metric_vector(
        fingerprint=fingerprint,
        metrics=metrics,
        sample_count=10,
        variance_or_uncertainty={"variance_classification": "stable", "per_metric": per_metric or {}},
        measurement_scope="local_engine_client",
        raw_evidence_refs=["r"],
        created_at=FIXED_TIME,
    )
    return {
        "workload_id": fingerprint["workload_id"],
        "fingerprint": fingerprint,
        "quality_gate": gate,
        "metric_vector": vector,
        "quality_status": gate["gate_status"],
        "problems": [],
        "telemetry_problems": ["telemetry note"],
    }


def m(value, direction="lower_is_better"):
    return {"value": value, "unit": "x", "direction": direction}


def decide(candidate, baseline, primary):
    selection = select_eligible_baseline(
        candidate["fingerprint"],
        [
            {
                "run_id": baseline["fingerprint"]["run_id"],
                "fingerprint": baseline["fingerprint"],
                "quality_gate": baseline["quality_gate"],
                "metric_vector": baseline["metric_vector"],
            }
        ],
        DEFAULT_REQUIRED_DIMENSIONS,
    )
    return decide_claim(
        candidate=candidate,
        selection=selection,
        regression_threshold_pct=10.0,
        improvement_threshold_pct=10.0,
        primary_metric=primary,
    )


class ClaimOnPrimaryMetricTests(unittest.TestCase):
    def test_claim_follows_the_primary_metric_and_other_metrics_stay_separate(self) -> None:
        base = vec_evidence("run-b", {"ttft_ms": m(100), "output_tokens_per_second": m(50, "higher_is_better"), "vram_mb": m(4000)})
        cand = vec_evidence("run-c", {"ttft_ms": m(60), "output_tokens_per_second": m(40, "higher_is_better"), "vram_mb": m(4000)})
        decision = decide(cand, base, "ttft_ms")
        self.assertEqual((decision["claim_status"], decision["efficiency_status"]), ("permitted", "improvement"))
        deltas = decision["metric_deltas"]
        self.assertEqual(deltas["ttft_ms"]["outcome"], "better")
        self.assertEqual(deltas["output_tokens_per_second"]["outcome"], "worse")
        self.assertEqual(deltas["vram_mb"]["outcome"], "within_range")
        self.assertEqual(decision["primary_metric"], "ttft_ms")

    def test_a_worse_side_metric_is_shown_but_does_not_change_the_claim(self) -> None:
        base = vec_evidence("run-b", {"ttft_ms": m(100), "vram_mb": m(4000)})
        cand = vec_evidence("run-c", {"ttft_ms": m(60), "vram_mb": m(9000)})
        decision = decide(cand, base, "ttft_ms")
        self.assertEqual(decision["efficiency_status"], "improvement")
        self.assertEqual(decision["metric_deltas"]["vram_mb"]["outcome"], "worse")

    def test_higher_is_better_primary(self) -> None:
        base = vec_evidence("run-b", {"output_tokens_per_second": m(50, "higher_is_better")})
        cand = vec_evidence("run-c", {"output_tokens_per_second": m(80, "higher_is_better")})
        self.assertEqual(decide(cand, base, "output_tokens_per_second")["efficiency_status"], "improvement")

    def test_missing_primary_metric_is_evidence_blocked_with_telemetry_reason(self) -> None:
        base = vec_evidence("run-b", {"ttft_ms": m(100)})
        cand = vec_evidence("run-c", {"vram_mb": m(1)})
        decision = decide(cand, base, "ttft_ms")
        self.assertEqual(decision["claim_status"], "evidence_blocked")
        self.assertIn("telemetry note", decision["blocked_reasons"])

    def test_stability_is_judged_per_primary_metric(self) -> None:
        base = vec_evidence("run-b", {"ttft_ms": m(100), "vram_mb": m(1)}, {"ttft_ms": "stable", "vram_mb": "unstable"})
        cand = vec_evidence("run-c", {"ttft_ms": m(60), "vram_mb": m(1)}, {"ttft_ms": "stable", "vram_mb": "unstable"})
        self.assertEqual(decide(cand, base, "ttft_ms")["claim_status"], "permitted")
        self.assertEqual(decide(cand, base, "vram_mb")["claim_status"], "no_claim_unstable")

    def test_informational_only_primary_cannot_claim(self) -> None:
        base = vec_evidence("run-b", {"output_tokens": m(64, "informational_only")})
        cand = vec_evidence("run-c", {"output_tokens": m(32, "informational_only")})
        self.assertEqual(decide(cand, base, "output_tokens")["claim_status"], "evidence_blocked")

    def test_direction_mismatch_on_a_side_metric_is_reported(self) -> None:
        base = vec_evidence("run-b", {"ttft_ms": m(100), "vram_mb": m(1)})
        cand = vec_evidence("run-c", {"ttft_ms": m(60), "vram_mb": m(1, "higher_is_better")})
        self.assertEqual(decide(cand, base, "ttft_ms")["metric_deltas"]["vram_mb"]["outcome"], "direction_mismatch")


TELEMETRY_EVAL = copy.deepcopy(EVALUATION)
TELEMETRY_EVAL["metrics"] = {
    "median_ms": "lower_is_better",
    "ttft_ms": "lower_is_better",
    "output_tokens_per_second": "higher_is_better",
    "vram_mb": "lower_is_better",
}
TELEMETRY_EVAL["primary_metric"] = "ttft_ms"
TELEMETRY_EVAL["telemetry_policy"] = {
    "telemetry_results_path": "telemetry/results.json",
    "percentile_metrics": ["ttft_ms"],
    "p95_min_samples": 5,
    "p99_min_samples": 50,
}


def write_telemetry(repo: Path, ttft: list[float], tps: float = 50.0, vram: float = 4000.0) -> None:
    (repo / "telemetry").mkdir(exist_ok=True)
    (repo / "telemetry" / "results.json").write_text(
        json.dumps(payload(ttft_ms=ttft, output_tokens_per_second=[tps] * 5, vram_mb=[vram] * 5)), encoding="utf-8"
    )


class EndToEndTelemetryTests(unittest.TestCase):
    def run_pair(self, first_ttft, second_ttft, **second):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        runs = []
        for ttft, extra in ((first_ttft, {}), (second_ttft, second)):
            write_quality(repo, 0.95)
            if ttft is not None:
                write_telemetry(repo, ttft, **extra)
            elif (repo / "telemetry" / "results.json").exists():
                (repo / "telemetry" / "results.json").unlink()
            write_v2_manifest(era_root, repo.name, copy.deepcopy(TELEMETRY_EVAL), threshold_pct=25.0)
            runs.append(
                execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
            )
        run_dir = runs[1]
        directory = run_dir / "evidence/efficiency/eval/eval_probe"
        load = lambda name: json.loads((directory / name).read_text(encoding="utf-8"))  # noqa: E731
        return runs, load("comparison.json"), load("metric_vector.json"), (run_dir / "review.md").read_text(encoding="utf-8")

    def test_ttft_claim_with_percentiles_side_metrics_and_review(self) -> None:
        good = [100, 101, 100, 99, 100, 101]
        fast = [60, 61, 60, 59, 60, 61]
        runs, comparison, vector, review = self.run_pair(good, fast, tps=30.0)
        self.assertEqual(comparison["primary_metric"], "ttft_ms")
        self.assertEqual((comparison["claim_status"], comparison["efficiency_status"]), ("permitted", "improvement"))
        self.assertIn("ttft_ms_p95", vector["metrics"])
        self.assertNotIn("ttft_ms_p99", vector["metrics"])
        self.assertEqual(comparison["metric_deltas"]["output_tokens_per_second"]["outcome"], "worse")
        self.assertTrue(any("telemetry_results:telemetry/results.json:sha256:" in ref for ref in vector["raw_evidence_refs"]))
        self.assertIn("local_engine_client", vector["measurement_scope"])
        for text in (
            "primary metric (the claim rests on this one only): `ttft_ms`",
            "| ttft_ms (primary) | lower_is_better |",
            "| output_tokens_per_second | higher_is_better |",
            "telemetry note: ttft_ms_p99 omitted",
        ):
            self.assertIn(text, review)
        result = validate_run_dir(runs[1])
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_missing_telemetry_blocks_the_ttft_claim(self) -> None:
        _, comparison, _, review = self.run_pair([100, 101, 100, 99, 100], None)
        self.assertEqual(comparison["claim_status"], "evidence_blocked")
        self.assertIn("Telemetry file", " ".join(comparison["blocked_reasons"]))
        self.assertIn("telemetry problem:", review)

    def test_changed_concurrency_is_incomparable_for_telemetry_workloads(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        write_quality(repo, 0.95)
        write_telemetry(repo, [100, 101, 100, 99, 100])
        runs = []
        for concurrency in (1, 8):
            evaluation = copy.deepcopy(TELEMETRY_EVAL)
            evaluation["execution_identity"]["concurrency"] = concurrency
            write_v2_manifest(era_root, repo.name, evaluation)
            runs.append(
                execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
            )
        comparison = json.loads((runs[1] / "evidence/efficiency/eval/eval_probe/comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(comparison["claim_status"], "incomparable")
        self.assertIn("execution.concurrency", " ".join(comparison["blocked_reasons"]))


if __name__ == "__main__":
    unittest.main()
