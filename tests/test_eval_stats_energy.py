from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_claims import decide_claim, select_eligible_baseline
from era_core.eval_comparability import DEFAULT_REQUIRED_DIMENSIONS
from era_core.eval_contracts import validate_metric_vector
from era_core.eval_lane import required_dimensions, validate_eval_policy, validate_sample_policy
from era_core.eval_stats import MIN_SAMPLES_FOR_CI, bootstrap_median_ci, intervals_overlap
from era_core.eval_telemetry import summarize_telemetry, validate_telemetry_policy
from era_core.hashing import sha256_json
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import make_fingerprint
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_lane import EVALUATION, write_quality, write_v2_manifest
from tests.test_eval_telemetry import decide, m, payload, vec_evidence


class BootstrapTests(unittest.TestCase):
    def test_deterministic_and_bounded(self) -> None:
        values = [10.0, 11.0, 12.0, 10.5, 11.5, 10.2, 11.8]
        first, second = bootstrap_median_ci(values), bootstrap_median_ci(list(reversed(values)))
        self.assertEqual(first, second)
        self.assertLessEqual(first["ci_low"], first["ci_high"])
        self.assertGreaterEqual(first["ci_low"], min(values))
        self.assertLessEqual(first["ci_high"], max(values))
        self.assertEqual((first["method"], first["resamples"], first["confidence"]), ("bootstrap_median_percentile", 1000, 0.95))

    def test_too_few_samples_gives_no_interval(self) -> None:
        self.assertIsNone(bootstrap_median_ci([1.0] * (MIN_SAMPLES_FOR_CI - 1)))
        self.assertIsNotNone(bootstrap_median_ci([1.0] * MIN_SAMPLES_FOR_CI))

    def test_constant_samples_give_a_point_interval(self) -> None:
        ci = bootstrap_median_ci([5.0] * 8)
        self.assertEqual((ci["ci_low"], ci["ci_high"]), (5.0, 5.0))

    def test_wider_spread_gives_wider_interval(self) -> None:
        tight = bootstrap_median_ci([10, 10.1, 9.9, 10, 10.2, 9.8, 10.1])
        wide = bootstrap_median_ci([5, 15, 8, 12, 20, 3, 18])
        self.assertGreater(wide["ci_high"] - wide["ci_low"], tight["ci_high"] - tight["ci_low"])

    def test_overlap(self) -> None:
        a, b, c = {"ci_low": 1, "ci_high": 5}, {"ci_low": 5, "ci_high": 9}, {"ci_low": 6, "ci_high": 9}
        self.assertTrue(intervals_overlap(a, b))
        self.assertFalse(intervals_overlap(a, c))
        self.assertIsNone(intervals_overlap(a, None))


class SamplePolicyTests(unittest.TestCase):
    def test_validation(self) -> None:
        self.assertEqual(validate_sample_policy({"warmup_iterations": 2, "min_samples": 5, "require_ci_separation": True}), [])
        for bad in ({"warmup_iterations": 21}, {"warmup_iterations": -1}, {"warmup_iterations": True},
                    {"min_samples": -1}, {"require_ci_separation": "yes"}, "x"):
            self.assertTrue(validate_sample_policy(bad), bad)

    def test_eval_policy_includes_sample_policy_errors(self) -> None:
        policy = copy.deepcopy(EVALUATION)
        policy["sample_policy"] = {"warmup_iterations": 99}
        self.assertTrue(validate_eval_policy(policy))


def with_intervals(run_id, value, low, high, samples=10, **kw):
    item = vec_evidence(run_id, {"ttft_ms": m(value)}, {"ttft_ms": "stable"}, **kw)
    uncertainty = item["metric_vector"]["variance_or_uncertainty"]
    uncertainty["uncertainty"] = {"ttft_ms": {"ci_low": low, "ci_high": high, "method": "bootstrap_median_percentile"}}
    uncertainty["per_metric_sample_count"] = {"ttft_ms": samples}
    vector = item["metric_vector"]
    vector["sha256"] = sha256_json({k: v for k, v in vector.items() if k != "sha256"})
    return item


def gate(candidate, baseline, **kwargs):
    selection = select_eligible_baseline(
        candidate["fingerprint"],
        [{"run_id": baseline["fingerprint"]["run_id"], **{k: baseline[k] for k in ("fingerprint", "quality_gate", "metric_vector")}}],
        DEFAULT_REQUIRED_DIMENSIONS,
    )
    return decide_claim(
        candidate=candidate, selection=selection, regression_threshold_pct=10.0, improvement_threshold_pct=10.0,
        primary_metric="ttft_ms", **kwargs,
    )


class ClaimPolicyTests(unittest.TestCase):
    def test_minimum_samples(self) -> None:
        base, cand = with_intervals("run-b", 100, 95, 105, samples=10), with_intervals("run-c", 60, 55, 65, samples=3)
        thin = gate(cand, base, min_samples=5)
        self.assertEqual(thin["claim_status"], "no_claim_unstable")
        self.assertIn("fewer than the required 5", thin["blocked_reasons"][0])
        self.assertIn("candidate", thin["blocked_reasons"][0])
        self.assertEqual(gate(cand, base, min_samples=3)["claim_status"], "permitted")

    def test_separated_intervals_allow_a_claim(self) -> None:
        base, cand = with_intervals("run-b", 100, 95, 105), with_intervals("run-c", 60, 55, 65)
        decision = gate(cand, base, require_ci_separation=True)
        self.assertEqual((decision["claim_status"], decision["efficiency_status"]), ("permitted", "improvement"))
        self.assertEqual(decision["metric_deltas"]["ttft_ms"]["candidate_interval"]["ci_low"], 55)

    def test_overlapping_intervals_block_the_claim(self) -> None:
        base, cand = with_intervals("run-b", 100, 50, 110), with_intervals("run-c", 60, 55, 65)
        decision = gate(cand, base, require_ci_separation=True)
        self.assertEqual(decision["claim_status"], "no_claim_unstable")
        self.assertIn("intervals", decision["blocked_reasons"][0])
        self.assertEqual(decision["efficiency_status"], "unstable")

    def test_missing_interval_blocks_when_separation_is_required(self) -> None:
        base, cand = vec_evidence("run-b", {"ttft_ms": m(100)}), vec_evidence("run-c", {"ttft_ms": m(60)})
        self.assertEqual(gate(cand, base, require_ci_separation=True)["claim_status"], "no_claim_unstable")
        self.assertEqual(gate(cand, base)["claim_status"], "permitted")

    def test_within_range_needs_no_separation(self) -> None:
        base, cand = with_intervals("run-b", 100, 50, 150), with_intervals("run-c", 102, 60, 140)
        self.assertEqual(gate(cand, base, require_ci_separation=True)["efficiency_status"], "within_range")


ENERGY_DIRECTIONS = {"energy_joules": "lower_is_better", "energy_per_token_j": "lower_is_better", "tasks_per_joule": "higher_is_better"}


def energy_payload(scope="gpu_counter_only", **samples):
    data = payload(**samples)
    data["energy"] = {"scope": scope, "source": "fixture"}
    return data


class EnergyTests(unittest.TestCase):
    samples = {"energy_joules": [10, 11, 10], "energy_per_token_j": [0.5, 0.5, 0.6], "tasks_per_joule": [2, 2, 2]}

    def test_scope_is_labelled_on_every_energy_metric(self) -> None:
        result = summarize_telemetry(energy_payload(**self.samples), ENERGY_DIRECTIONS, {"energy_scope": "gpu_counter_only"})
        self.assertEqual(result["problems"], [])
        for name in ENERGY_DIRECTIONS:
            self.assertEqual(result["metrics"][name]["scope"], "gpu_counter_only")

    def test_missing_declared_scope_leaves_energy_out(self) -> None:
        result = summarize_telemetry(energy_payload(**self.samples), ENERGY_DIRECTIONS, {})
        self.assertEqual(result["metrics"], {})
        self.assertIn("need telemetry_policy.energy_scope", result["problems"][0])

    def test_scope_mismatch_leaves_energy_out(self) -> None:
        result = summarize_telemetry(
            energy_payload(scope="gpu_counter_only", **self.samples), ENERGY_DIRECTIONS, {"energy_scope": "system_wall"}
        )
        self.assertEqual(result["metrics"], {})
        self.assertIn("scope mismatch", result["problems"][0])

    def test_gpu_counter_is_never_called_wall_power(self) -> None:
        from era_core.eval_telemetry import ENERGY_SCOPES

        self.assertIn("Not wall power", ENERGY_SCOPES["gpu_counter_only"])
        self.assertIn("Not wall power", ENERGY_SCOPES["cpu_package"])

    def test_unknown_scope_is_rejected_by_policy(self) -> None:
        self.assertTrue(validate_telemetry_policy({"telemetry_results_path": "x", "energy_scope": "magic"}))
        self.assertEqual(validate_telemetry_policy({"telemetry_results_path": "x", "energy_scope": "system_wall"}), [])

    def test_vector_validation_requires_scope_on_energy_metrics(self) -> None:
        item = vec_evidence("run-b", {"energy_joules": m(10)})
        self.assertTrue(any("measurement scope" in e for e in validate_metric_vector(item["metric_vector"])))
        item = vec_evidence("run-b", {"energy_joules": {**m(10), "scope": "system_wall"}})
        self.assertEqual(validate_metric_vector(item["metric_vector"]), [])
        item = vec_evidence("run-b", {"energy_joules_p95": {**m(10), "scope": "bogus"}})
        self.assertTrue(validate_metric_vector(item["metric_vector"]))

    def test_energy_scope_change_is_incomparable(self) -> None:
        policy = {**EVALUATION, "telemetry_policy": {"telemetry_results_path": "x", "energy_scope": "gpu_counter_only"}}
        self.assertIn("execution.energy_scope", required_dimensions(policy))
        base = vec_evidence("run-b", {"energy_joules": {**m(10), "scope": "gpu_counter_only"}}, **{"execution_identity.energy_scope": "gpu_counter_only"})
        cand = vec_evidence("run-c", {"energy_joules": {**m(5), "scope": "system_wall"}}, **{"execution_identity.energy_scope": "system_wall"})
        selection = select_eligible_baseline(
            cand["fingerprint"],
            [{"run_id": "run-b", **{k: base[k] for k in ("fingerprint", "quality_gate", "metric_vector")}}],
            required_dimensions(policy),
        )
        decision = decide_claim(
            candidate=cand, selection=selection, regression_threshold_pct=10.0, improvement_threshold_pct=10.0,
            primary_metric="energy_joules",
        )
        self.assertEqual(decision["claim_status"], "incomparable")
        self.assertIn("execution.energy_scope", " ".join(decision["blocked_reasons"]))

    def test_energy_metrics_report_separately_with_scope(self) -> None:
        base = vec_evidence("run-b", {"ttft_ms": m(100), "energy_joules": {**m(10), "scope": "gpu_counter_only"}})
        cand = vec_evidence("run-c", {"ttft_ms": m(60), "energy_joules": {**m(12), "scope": "gpu_counter_only"}})
        decision = decide(cand, base, "ttft_ms")
        self.assertEqual(decision["metric_deltas"]["energy_joules"]["scope"], "gpu_counter_only")
        self.assertEqual(decision["metric_deltas"]["energy_joules"]["outcome"], "worse")
        self.assertEqual(decision["claim_status"], "permitted")


WARM_EVAL = copy.deepcopy(EVALUATION)
WARM_EVAL["metrics"] = {"median_ms": "lower_is_better", "energy_joules": "lower_is_better"}
WARM_EVAL["sample_policy"] = {"warmup_iterations": 2, "min_samples": 3, "require_ci_separation": False}
WARM_EVAL["telemetry_policy"] = {"telemetry_results_path": "telemetry/results.json", "energy_scope": "gpu_counter_only"}


class EndToEndTests(unittest.TestCase):
    def make(self, energy_scope="gpu_counter_only"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        write_quality(repo, 0.95)
        (repo / "telemetry").mkdir()
        (repo / "telemetry" / "results.json").write_text(
            json.dumps(energy_payload(scope=energy_scope, energy_joules=[10, 10, 11, 10, 10, 11])), encoding="utf-8"
        )
        counter = root / "counter"
        command = ["python3", "-c", "import sys,pathlib;p=pathlib.Path(sys.argv[1]);p.write_text(p.read_text()+'x' if p.exists() else 'x')", str(counter)]
        write_v2_manifest(era_root, repo.name, copy.deepcopy(WARM_EVAL), command)
        run_dir = execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
        return run_dir, counter

    def test_warmups_run_but_are_not_measured(self) -> None:
        run_dir, counter = self.make()
        self.assertEqual(len(counter.read_text()), 5)  # 2 warmup + 3 measured
        bundle = json.loads((run_dir / "evidence/efficiency/efficiency_evidence_bundle.json").read_text(encoding="utf-8"))
        result = bundle["command_results"][0]["lane_metadata"]
        self.assertEqual(result["warmup_iterations"], 2)
        self.assertEqual(len(result["iteration_durations_ms"]), 3)
        vector = json.loads((run_dir / "evidence/efficiency/eval/eval_probe/metric_vector.json").read_text(encoding="utf-8"))
        self.assertEqual(vector["variance_or_uncertainty"]["warmup_iterations"], 2)
        self.assertEqual(vector["variance_or_uncertainty"]["per_metric_sample_count"]["median_ms"], 3)
        self.assertIn("omitted", vector["variance_or_uncertainty"]["uncertainty"]["median_ms"])
        self.assertIn("ci_low", vector["variance_or_uncertainty"]["uncertainty"]["energy_joules"])

    def test_energy_scope_is_in_fingerprint_vector_and_review(self) -> None:
        run_dir, _ = self.make()
        directory = run_dir / "evidence/efficiency/eval/eval_probe"
        fingerprint = json.loads((directory / "fingerprint.json").read_text(encoding="utf-8"))
        vector = json.loads((directory / "metric_vector.json").read_text(encoding="utf-8"))
        self.assertEqual(fingerprint["execution_identity"]["energy_scope"], "gpu_counter_only")
        self.assertEqual(vector["metrics"]["energy_joules"]["scope"], "gpu_counter_only")
        review = (run_dir / "review.md").read_text(encoding="utf-8")
        self.assertIn("energy scope for `energy_joules`: `gpu_counter_only` (GPU counter only. Not wall power.)", review)
        self.assertIn("warmup iterations discarded: `2`", review)
        result = validate_run_dir(run_dir)
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_scope_mismatch_reports_a_telemetry_problem(self) -> None:
        run_dir, _ = self.make(energy_scope="system_wall")
        review = (run_dir / "review.md").read_text(encoding="utf-8")
        self.assertIn("telemetry problem: Energy metric `energy_joules` left out. Energy scope mismatch", review)
        vector = json.loads((run_dir / "evidence/efficiency/eval/eval_probe/metric_vector.json").read_text(encoding="utf-8"))
        self.assertNotIn("energy_joules", vector["metrics"])


if __name__ == "__main__":
    unittest.main()
