from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from era_cli.commands.run import execute_run
from era_core.eval_agent import (
    AGENT_SUBJECT_FIELDS,
    read_agent_evidence,
    summarize_agent,
    validate_agent_policy,
    validate_agent_subject,
)
from era_core.eval_lane import required_dimensions, validate_eval_policy
from era_core.eval_stats import bootstrap_ratio_ci, wilson_interval
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import FakeContainedSandbox
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_lane import EVALUATION, write_v2_manifest

DIRECTIONS = {
    "task_success_rate": "higher_is_better",
    "steps_per_task": "lower_is_better",
    "tool_calls_per_task": "lower_is_better",
    "tokens_per_task": "lower_is_better",
    "wall_time_ms_per_task": "lower_is_better",
    "api_cost_usd_per_successful_task": "lower_is_better",
    "joules_per_successful_task": "lower_is_better",
}
AGENT_SUBJECT = {
    "agent_revision": "agent-r1",
    "model_lane": "local-lane-a",
    "tool_policy_hash": "tp1",
    "prompt_program_hash": "pp1",
    "step_budget": 20,
    "token_budget": 20000,
}


def task(index, success=True, steps=6, calls=3, inp=1000, out=200, wall=5000, cost=0.02, energy=100.0):
    entry = {
        "task_id": f"t{index}", "success": success, "steps": steps, "tool_calls": calls,
        "input_tokens": inp, "output_tokens": out, "wall_time_ms": wall,
    }
    if cost is not None:
        entry["api_cost_usd"] = cost
    if energy is not None:
        entry["energy_joules"] = energy
    return entry


def evidence(tasks, scope="system_wall"):
    data = {"schema_version": "AgentRunEvidence.v1", "measurement_scope": "agent_harness", "tasks": tasks}
    if scope:
        data["energy"] = {"scope": scope}
    return data


class SummaryTests(unittest.TestCase):
    def test_metrics_and_units(self) -> None:
        tasks = [task(i, success=i < 8, steps=5 + i % 3, cost=0.02) for i in range(10)]
        result = summarize_agent(evidence(tasks), DIRECTIONS, {"energy_scope": "system_wall"})
        metrics = result["metrics"]
        self.assertEqual(metrics["task_success_rate"]["value"], 0.8)
        self.assertEqual(metrics["tokens_per_task"]["value"], 1200)
        self.assertAlmostEqual(metrics["api_cost_usd_per_successful_task"]["value"], 0.2 / 8)
        self.assertAlmostEqual(metrics["joules_per_successful_task"]["value"], 1000 / 8)
        self.assertEqual(metrics["joules_per_successful_task"]["scope"], "system_wall")
        self.assertEqual(metrics["api_cost_usd_per_successful_task"]["unit"], "USD/task")
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["success_rate"], 0.8)

    def test_failed_tasks_still_cost_money(self) -> None:
        cheap_fail = [task(0, success=True, cost=0.01)] + [task(i, success=False, cost=0.01) for i in range(1, 10)]
        result = summarize_agent(evidence(cheap_fail), DIRECTIONS, {"energy_scope": "system_wall"})
        self.assertAlmostEqual(result["metrics"]["api_cost_usd_per_successful_task"]["value"], 0.1)

    def test_no_success_leaves_ratios_out_and_says_why(self) -> None:
        result = summarize_agent(evidence([task(i, success=False) for i in range(6)]), DIRECTIONS, {"energy_scope": "system_wall"})
        self.assertNotIn("api_cost_usd_per_successful_task", result["metrics"])
        self.assertNotIn("joules_per_successful_task", result["metrics"])
        self.assertEqual(result["metrics"]["task_success_rate"]["value"], 0.0)
        self.assertTrue(any("no task succeeded" in p for p in result["problems"]))

    def test_missing_cost_or_energy_on_any_task_leaves_the_metric_out(self) -> None:
        tasks = [task(i) for i in range(6)]
        del tasks[3]["api_cost_usd"]
        del tasks[2]["energy_joules"]
        result = summarize_agent(evidence(tasks), DIRECTIONS, {"energy_scope": "system_wall"})
        self.assertNotIn("api_cost_usd_per_successful_task", result["metrics"])
        self.assertNotIn("joules_per_successful_task", result["metrics"])
        self.assertEqual(len([p for p in result["problems"] if "missing or invalid" in p]), 2)

    def test_energy_scope_rules(self) -> None:
        tasks = [task(i) for i in range(6)]
        undeclared = summarize_agent(evidence(tasks), DIRECTIONS, {})
        self.assertTrue(any("not declared" in p for p in undeclared["problems"]))
        mismatch = summarize_agent(evidence(tasks, scope="gpu_counter_only"), DIRECTIONS, {"energy_scope": "system_wall"})
        self.assertTrue(any("scope mismatch" in p for p in mismatch["problems"]))
        self.assertNotIn("joules_per_successful_task", mismatch["metrics"])

    def test_bad_tasks_are_left_out_and_named(self) -> None:
        tasks = [task(0), task(0), {"task_id": "x"}, task(2, steps=-1), task(3), {"task_id": "y", "success": "yes"}]
        result = summarize_agent(evidence(tasks), {"steps_per_task": "lower_is_better"}, {})
        self.assertEqual(result["task_count"], 2)
        self.assertEqual(len(result["problems"]), 4)

    def test_only_declared_metrics_appear_and_there_is_no_score(self) -> None:
        result = summarize_agent(evidence([task(i) for i in range(5)]), {"steps_per_task": "lower_is_better"}, {})
        self.assertEqual(list(result["metrics"]), ["steps_per_task"])
        self.assertFalse(any("score" in name for name in result["metrics"]))
        self.assertFalse({"score", "promotion_score", "combined"} & set(result))

    def test_empty_evidence(self) -> None:
        result = summarize_agent(evidence([]), DIRECTIONS, {})
        self.assertEqual(result["metrics"], {})
        self.assertIsNone(result["success_rate"])

    def test_task_level_spread_is_not_called_unstable(self) -> None:
        tasks = [task(i, steps=2 + 10 * (i % 2)) for i in range(10)]
        result = summarize_agent(evidence(tasks), DIRECTIONS, {})
        self.assertEqual(result["per_metric_variance"]["steps_per_task"], "task_level")


class IntervalTests(unittest.TestCase):
    def test_wilson(self) -> None:
        interval = wilson_interval(8, 10)
        self.assertLess(interval["ci_low"], 0.8)
        self.assertGreater(interval["ci_high"], 0.8)
        self.assertGreaterEqual(interval["ci_low"], 0.0)
        self.assertLessEqual(wilson_interval(10, 10)["ci_high"], 1.0)
        self.assertGreater(wilson_interval(10, 10)["ci_low"], 0.6)
        self.assertIsNone(wilson_interval(0, 0))
        self.assertGreater(wilson_interval(80, 100)["ci_low"], wilson_interval(8, 10)["ci_low"])

    def test_ratio_bootstrap_is_deterministic_and_needs_data(self) -> None:
        costs, wins = [0.02] * 10, [1] * 8 + [0] * 2
        first, second = bootstrap_ratio_ci(costs, wins), bootstrap_ratio_ci(list(costs), list(wins))
        self.assertEqual(first, second)
        self.assertLessEqual(first["ci_low"], 0.025)
        self.assertGreaterEqual(first["ci_high"], 0.025)
        self.assertIsNone(bootstrap_ratio_ci([0.02] * 3, [1, 1, 1]))
        self.assertIsNone(bootstrap_ratio_ci([0.02] * 8, [0] * 8))


class ReadAndPolicyTests(unittest.TestCase):
    def test_read_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "agent").mkdir()
            path = root / "agent" / "runs.json"
            path.write_text(json.dumps(evidence([task(0)])), encoding="utf-8")
            _, digest, problems = read_agent_evidence(root, ".", "agent/runs.json")
            self.assertEqual((problems, bool(digest)), ([], True))
            self.assertIn("escapes", read_agent_evidence(root, ".", "../x")[2][0])
            self.assertIn("does not exist", read_agent_evidence(root, ".", "agent/no.json")[2][0])
            path.write_text("x", encoding="utf-8")
            self.assertIn("not valid JSON", read_agent_evidence(root, ".", "agent/runs.json")[2][0])
            path.write_text(json.dumps({"schema_version": "Other"}), encoding="utf-8")
            self.assertIn("is not AgentRunEvidence.v1", read_agent_evidence(root, ".", "agent/runs.json")[2][0])
            path.write_text(json.dumps({"schema_version": "AgentRunEvidence.v1"}), encoding="utf-8")
            self.assertIn("needs tasks", read_agent_evidence(root, ".", "agent/runs.json")[2][0])

    def test_agent_subject_fields_are_required(self) -> None:
        self.assertEqual(validate_agent_subject(AGENT_SUBJECT), [])
        for field in AGENT_SUBJECT_FIELDS:
            partial = {k: v for k, v in AGENT_SUBJECT.items() if k != field}
            self.assertTrue(any(field in e for e in validate_agent_subject(partial)), field)
        self.assertEqual(len(validate_agent_subject(None)), len(AGENT_SUBJECT_FIELDS))

    def test_agent_policy_validation(self) -> None:
        self.assertEqual(validate_agent_policy({"agent_evidence_path": "a"}, "agent", AGENT_SUBJECT), [])
        self.assertTrue(validate_agent_policy({"agent_evidence_path": "a"}, "local_model", AGENT_SUBJECT))
        self.assertTrue(validate_agent_policy({}, "agent", AGENT_SUBJECT))
        self.assertTrue(validate_agent_policy({"agent_evidence_path": "a", "energy_scope": "magic"}, "agent", AGENT_SUBJECT))

    def test_eval_policy_for_an_agent(self) -> None:
        policy = agent_eval()
        self.assertEqual(validate_eval_policy(policy), [])
        del policy["subject_identity"]["tool_policy_hash"]
        self.assertTrue(any("tool_policy_hash" in e for e in validate_eval_policy(policy)))

    def test_agent_identity_and_hardware_become_required_dimensions(self) -> None:
        dims = required_dimensions(agent_eval())
        for field in AGENT_SUBJECT_FIELDS:
            self.assertIn(f"subject.{field}", dims)
        self.assertIn("execution.concurrency", dims)
        self.assertIn("execution.energy_scope", dims)


def agent_eval(primary="api_cost_usd_per_successful_task", floors=None):
    policy = copy.deepcopy(EVALUATION)
    policy["subject_kind"] = "agent"
    policy["subject_identity"] = copy.deepcopy(AGENT_SUBJECT)
    policy["quality_gate_policy"] = {
        "quality_floors": floors or {"task_success_rate": {"min": 0.7}},
        "quality_results_path": "quality/results.json",
    }
    policy["metrics"] = dict(DIRECTIONS)
    policy["primary_metric"] = primary
    policy["agent_policy"] = {"agent_evidence_path": "agent/runs.json", "energy_scope": "system_wall"}
    policy["sample_policy"] = {"min_samples": 10, "require_ci_separation": False}
    return policy


class EndToEndAgentTests(unittest.TestCase):
    def run_pair(self, first, second, second_subject=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        runs = []
        for tasks, subject in ((first, None), (second, second_subject)):
            (repo / "agent").mkdir(exist_ok=True)
            (repo / "agent" / "runs.json").write_text(json.dumps(evidence(tasks)), encoding="utf-8")
            policy = agent_eval()
            if subject:
                policy["subject_identity"].update(subject)
            write_v2_manifest(era_root, repo.name, policy, threshold_pct=20.0)
            with mock.patch("era_cli.commands.run.resolve_sandbox", return_value=FakeContainedSandbox()):
                runs.append(
                    execute_run(
                        repo_path=repo,
                        lanes=["efficiency"],
                        mode="full",
                        artifacts_root=era_root / "artifacts" / "era-runs",
                        target_trust="untrusted",
                    )
                )
        load = lambda name: json.loads((runs[1] / "evidence/efficiency/eval" / "eval_probe" / name).read_text(encoding="utf-8"))  # noqa: E731
        return runs, load

    def test_cheaper_per_success_with_the_same_success_rate_is_an_improvement(self) -> None:
        baseline = [task(i, success=i < 9, cost=0.04) for i in range(12)]
        cheaper = [task(i, success=i < 9, cost=0.02) for i in range(12)]
        runs, load = self.run_pair(baseline, cheaper)
        comparison = load("comparison.json")
        self.assertEqual((comparison["claim_status"], comparison["efficiency_status"]), ("permitted", "improvement"))
        self.assertEqual(comparison["primary_metric"], "api_cost_usd_per_successful_task")
        vector = load("metric_vector.json")
        self.assertEqual(vector["metrics"]["task_success_rate"]["value"], 0.75)
        deltas = comparison["metric_deltas"]
        self.assertEqual(deltas["api_cost_usd_per_successful_task"]["outcome"], "better")
        self.assertEqual(deltas["task_success_rate"]["outcome"], "within_range")
        self.assertIn("ci_low", deltas["task_success_rate"]["candidate_interval"])
        self.assertEqual(vector["variance_or_uncertainty"]["per_metric"]["steps_per_task"], "task_level")
        result = validate_run_dir(runs[1])
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_cheaper_because_it_fails_is_quality_blocked(self) -> None:
        baseline = [task(i, success=i < 9, cost=0.04) for i in range(12)]
        cheap_and_failing = [task(i, success=i < 3, cost=0.005) for i in range(12)]
        _, load = self.run_pair(baseline, cheap_and_failing)
        self.assertEqual(load("quality_gate.json")["gate_status"], "failed")
        self.assertEqual(load("comparison.json")["claim_status"], "quality_blocked")
        self.assertEqual(load("comparison.json")["efficiency_status"], "not_evaluated")

    def test_success_rate_comes_from_the_hashed_evidence(self) -> None:
        good = [task(i, success=True) for i in range(12)]
        runs, load = self.run_pair(good, good)
        gate = load("quality_gate.json")
        self.assertEqual(gate["metric_results"]["task_success_rate"], 1.0)
        self.assertTrue(any(ref.startswith("agent_evidence:agent/runs.json:sha256:") for ref in gate["raw_evidence_refs"]))

    def test_changed_tool_policy_is_incomparable(self) -> None:
        good = [task(i) for i in range(12)]
        _, load = self.run_pair(good, good, second_subject={"tool_policy_hash": "tp2"})
        comparison = load("comparison.json")
        self.assertEqual(comparison["claim_status"], "incomparable")
        self.assertIn("subject.tool_policy_hash", " ".join(comparison["blocked_reasons"]))

    def test_thin_task_counts_give_no_claim(self) -> None:
        few = [task(i, cost=0.04) for i in range(6)]
        few_cheap = [task(i, cost=0.02) for i in range(6)]
        _, load = self.run_pair(few, few_cheap)
        self.assertEqual(load("comparison.json")["claim_status"], "no_claim_unstable")
        self.assertIn("fewer than the required 10", " ".join(load("comparison.json")["blocked_reasons"]))

    def test_missing_cost_blocks_a_cost_claim_and_the_review_says_why(self) -> None:
        with_cost = [task(i, cost=0.04) for i in range(12)]
        no_cost = [task(i, cost=None) for i in range(12)]
        runs, load = self.run_pair(with_cost, no_cost)
        comparison = load("comparison.json")
        self.assertEqual(comparison["claim_status"], "evidence_blocked")
        review = (runs[1] / "review.md").read_text(encoding="utf-8")
        self.assertIn("agent evidence problem: Metric `api_cost_usd_per_successful_task` left out", review)

    def test_review_shows_each_agent_metric_on_its_own_row(self) -> None:
        good = [task(i) for i in range(12)]
        runs, _ = self.run_pair(good, good)
        review = (runs[1] / "review.md").read_text(encoding="utf-8")
        for name in ("task_success_rate", "steps_per_task", "tokens_per_task", "joules_per_successful_task"):
            self.assertIn(f"| {name} |", review)
        self.assertIn("| api_cost_usd_per_successful_task (primary) |", review)
        self.assertIn("energy scope for `joules_per_successful_task`: `system_wall`", review)


if __name__ == "__main__":
    unittest.main()
