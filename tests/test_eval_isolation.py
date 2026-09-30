from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from era_cli.commands.run import execute_run
from era_core.eval_claims import decide_claim, select_eligible_baseline
from era_core.eval_comparability import DEFAULT_REQUIRED_DIMENSIONS
from era_core.eval_contracts import validate_quality_efficiency_comparison
from era_core.eval_isolation import (
    RISK_TRAITS,
    build_isolation_receipt,
    evaluate_isolation,
    isolation_requirement,
    validate_isolation_receipt,
    validate_workload_traits,
)
from era_core.eval_lane import ISOLATION_DIMENSIONS, required_dimensions, validate_eval_policy
from era_core.hashing import sha256_json, sha256_path, write_json
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import FakeContainedSandbox, make_fingerprint
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_agent import AGENT_SUBJECT, agent_eval, evidence as agent_evidence, task
from tests.test_eval_claims import evidence
from tests.test_eval_lane import EVALUATION, write_quality, write_v2_manifest

CONTAINED = {"sandbox": "contained", "sandbox_backend": "unshare", "network": "isolated", "target_filesystem": "overlay_protected"}
OPEN = {"sandbox": "none", "sandbox_backend": "none", "network": "host", "target_filesystem": "writable"}
EVAL = "evidence/efficiency/eval/eval_probe"


def receipt(posture, required, reasons=("workload trait `agentic`",), trust="operator_trusted"):
    return build_isolation_receipt(
        fingerprint=make_fingerprint(),
        posture=posture,
        target_trust=trust,
        read_only_invariant_scope="enforced_by_overlay" if posture["sandbox"] == "contained" else "target_git_tree_only",
        required=required,
        required_reasons=list(reasons) if required else [],
    )


class RequirementTests(unittest.TestCase):
    def test_agents_and_risk_traits_require_isolation(self) -> None:
        self.assertEqual(isolation_requirement(EVALUATION), (False, []))
        required, reasons = isolation_requirement({**EVALUATION, "subject_kind": "agent"})
        self.assertTrue(required)
        self.assertIn("subject_kind is agent", reasons)
        for trait in sorted(RISK_TRAITS):
            self.assertTrue(isolation_requirement({**EVALUATION, "workload_traits": [trait]})[0], trait)

    def test_no_manifest_field_turns_the_requirement_off(self) -> None:
        policy = {**EVALUATION, "workload_traits": ["agentic"], "isolation_required": False, "isolation_policy": {"required": False}}
        self.assertTrue(isolation_requirement(policy)[0])

    def test_trait_validation(self) -> None:
        self.assertEqual(validate_workload_traits({"workload_traits": ["agentic", "mcp_tools"]}), [])
        self.assertTrue(validate_workload_traits({"workload_traits": ["vibes"]}))
        self.assertTrue(validate_workload_traits({"workload_traits": "agentic"}))
        bad = copy.deepcopy(EVALUATION)
        bad["workload_traits"] = ["vibes"]
        self.assertTrue(validate_eval_policy(bad))

    def test_status(self) -> None:
        self.assertEqual(evaluate_isolation(CONTAINED, True), "satisfied")
        self.assertEqual(evaluate_isolation(OPEN, True), "unsatisfied")
        self.assertEqual(evaluate_isolation(OPEN, False), "not_required")
        for key, value in (("network", "host"), ("target_filesystem", "writable"), ("sandbox", "none")):
            self.assertEqual(evaluate_isolation({**CONTAINED, key: value}, True), "unsatisfied", key)

    def test_posture_is_a_required_comparison_dimension(self) -> None:
        dims = required_dimensions(copy.deepcopy(EVALUATION))
        for name in ISOLATION_DIMENSIONS:
            self.assertIn(name, dims)


class ReceiptTests(unittest.TestCase):
    def test_contained_receipt_validates_and_states_limits(self) -> None:
        r = receipt(CONTAINED, True)
        self.assertEqual(r["status"], "satisfied")
        self.assertEqual(r["provider"], "era_core.sandbox")
        self.assertIn("operator ruling 2", r["provider_authority"])
        self.assertTrue(any("not a full jail" in item for item in r["limitations"]))
        self.assertEqual(validate_isolation_receipt(r), [])

    def test_unsatisfied_and_not_required_validate(self) -> None:
        self.assertEqual(receipt(OPEN, True)["status"], "unsatisfied")
        self.assertEqual(validate_isolation_receipt(receipt(OPEN, True)), [])
        self.assertEqual(receipt(OPEN, False)["status"], "not_required")
        self.assertEqual(validate_isolation_receipt(receipt(OPEN, False)), [])

    def test_forged_status_fails_even_when_resealed(self) -> None:
        forged = receipt(OPEN, True)
        forged["status"] = "satisfied"
        forged["sha256"] = sha256_json({k: v for k, v in forged.items() if k != "sha256"})
        self.assertTrue(any("contradicts its posture" in e for e in validate_isolation_receipt(forged)))

    def test_other_provider_limits_and_reasons(self) -> None:
        r = receipt(CONTAINED, True)
        for change, needle in (
            ({"provider": "somebody_else"}, "authorized provider"),
            ({"limitations": []}, "limitations"),
            ({"required_reasons": []}, "names no reason"),
        ):
            bad = {**r, **change}
            bad["sha256"] = sha256_json({k: v for k, v in bad.items() if k != "sha256"})
            self.assertTrue(any(needle in e for e in validate_isolation_receipt(bad)), needle)

    def test_tamper_fails(self) -> None:
        r = receipt(CONTAINED, True)
        self.assertTrue(any("sha256 mismatch" in e for e in validate_isolation_receipt({**r, "run_id": "x"})))


def claim(isolation_status, quality="passed", accuracy=0.95, with_baseline=True):
    candidate = evidence(median=50, accuracy=accuracy)
    priors = [
        {"run_id": "run-b", **{k: v for k, v in evidence("run-b", 100).items() if k in ("fingerprint", "quality_gate", "metric_vector")}}
    ] if with_baseline else []
    selection = select_eligible_baseline(candidate["fingerprint"], priors, DEFAULT_REQUIRED_DIMENSIONS)
    return decide_claim(
        candidate=candidate, selection=selection, regression_threshold_pct=10.0, improvement_threshold_pct=10.0,
        isolation_status=isolation_status,
    )


class ClaimGateTests(unittest.TestCase):
    def test_unsatisfied_isolation_blocks_every_claim(self) -> None:
        for with_baseline in (True, False):
            decision = claim("unsatisfied", with_baseline=with_baseline)
            self.assertEqual(decision["claim_status"], "evidence_blocked", with_baseline)
            self.assertEqual(decision["efficiency_status"], "not_evaluated")
            self.assertIn("Isolation is required", decision["blocked_reasons"][0])

    def test_quality_outcomes_stay_visible_without_isolation(self) -> None:
        self.assertEqual(claim("unsatisfied", accuracy=0.1)["claim_status"], "quality_blocked")

    def test_satisfied_and_not_required_allow_a_claim(self) -> None:
        for status in ("satisfied", "not_required"):
            self.assertEqual(claim(status)["claim_status"], "permitted", status)

    def test_comparison_contract_rejects_a_claim_without_isolation(self) -> None:
        from tests.test_eval_contracts import make_comparison

        self.assertTrue(validate_quality_efficiency_comparison(make_comparison(isolation_status="unsatisfied")))
        self.assertEqual(validate_quality_efficiency_comparison(make_comparison(isolation_status="satisfied")), [])
        blocked = make_comparison(
            isolation_status="unsatisfied", claim_status="evidence_blocked", efficiency_status="not_evaluated",
            comparability_status="unknown", blocked_reasons=["x"],
        )
        self.assertEqual(validate_quality_efficiency_comparison(blocked), [])


class EndToEndIsolationTests(unittest.TestCase):
    def run_agent_pair(self, contained=True, traits=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        runs = []
        for _ in range(2):
            (repo / "agent").mkdir(exist_ok=True)
            (repo / "agent" / "runs.json").write_text(json.dumps(agent_evidence([task(i) for i in range(12)])), encoding="utf-8")
            write_v2_manifest(era_root, repo.name, agent_eval(), threshold_pct=20.0)
            patch = mock.patch("era_cli.commands.run.resolve_sandbox", return_value=FakeContainedSandbox() if contained else None)
            with patch:
                runs.append(
                    execute_run(
                        repo_path=repo, lanes=["efficiency"], mode="full",
                        artifacts_root=era_root / "artifacts" / "era-runs",
                        target_trust="untrusted" if contained else "operator_trusted",
                    )
                )
        load = lambda name: json.loads((runs[1] / EVAL / name).read_text(encoding="utf-8"))  # noqa: E731
        return runs, load

    def test_contained_agent_run_is_satisfied_and_validates(self) -> None:
        runs, load = self.run_agent_pair(contained=True)
        receipt_ = load("isolation_receipt.json")
        self.assertEqual(receipt_["status"], "satisfied")
        self.assertTrue(receipt_["isolation_required"])
        self.assertEqual(load("comparison.json")["isolation_status"], "satisfied")
        self.assertEqual(load("fingerprint.json")["execution_identity"]["sandbox"], "contained")
        self.assertNotEqual(load("comparison.json")["claim_status"], "evidence_blocked")
        result = validate_run_dir(runs[1])
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))
        review = (runs[1] / "review.md").read_text(encoding="utf-8")
        for text in ("isolation: `satisfied` (provider `era_core.sandbox`)", "required because: subject_kind is agent", "limitation: A contained run is not a full jail"):
            self.assertIn(text, review)

    def test_uncontained_agent_run_gets_no_claim(self) -> None:
        runs, load = self.run_agent_pair(contained=False)
        self.assertEqual(load("isolation_receipt.json")["status"], "unsatisfied")
        comparison = load("comparison.json")
        self.assertEqual(comparison["claim_status"], "evidence_blocked")
        self.assertIn("Isolation is required", " ".join(comparison["blocked_reasons"]))
        review = (runs[1] / "review.md").read_text(encoding="utf-8")
        self.assertIn("no claim is made: the run was not contained", review)
        result = validate_run_dir(runs[1])
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_plain_workloads_are_not_required_to_be_contained(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        write_quality(repo, 0.95)
        write_v2_manifest(era_root, repo.name)
        run_dir = execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
        receipt_ = json.loads((run_dir / EVAL / "isolation_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual((receipt_["status"], receipt_["isolation_required"]), ("not_required", False))

    def test_a_contained_run_and_an_open_run_do_not_compare(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        write_quality(repo, 0.95)
        runs = []
        for sandbox in (None, FakeContainedSandbox()):
            write_v2_manifest(era_root, repo.name)
            with mock.patch("era_cli.commands.run.resolve_sandbox", return_value=sandbox):
                runs.append(
                    execute_run(
                        repo_path=repo, lanes=["efficiency"], mode="full",
                        artifacts_root=era_root / "artifacts" / "era-runs",
                        target_trust="operator_trusted",
                    )
                )
        comparison = json.loads((runs[1] / EVAL / "comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(comparison["claim_status"], "incomparable")
        self.assertIn("execution.sandbox", " ".join(comparison["blocked_reasons"]))

    def test_forged_receipt_status_is_caught_by_run_validation(self) -> None:
        runs, load = self.run_agent_pair(contained=False)
        forged = load("isolation_receipt.json")
        forged["status"] = "satisfied"
        forged["sha256"] = sha256_json({k: v for k, v in forged.items() if k != "sha256"})
        write_json(runs[1] / EVAL / "isolation_receipt.json", forged)
        hashes = json.loads((runs[1] / "hashes.json").read_text(encoding="utf-8"))
        for entry in hashes["entries"]:
            entry["sha256"] = sha256_path(runs[1] / entry["path"])
        write_json(runs[1] / "hashes.json", hashes)
        self.assertFalse(validate_run_dir(runs[1])["ok"])

    def test_a_receipt_that_disagrees_with_the_fingerprint_is_caught(self) -> None:
        runs, load = self.run_agent_pair(contained=False)
        forged = load("isolation_receipt.json")
        forged["posture"] = {**forged["posture"], "sandbox": "contained", "network": "isolated", "target_filesystem": "overlay_protected"}
        forged["status"] = "satisfied"
        forged["sha256"] = sha256_json({k: v for k, v in forged.items() if k != "sha256"})
        write_json(runs[1] / EVAL / "isolation_receipt.json", forged)
        hashes = json.loads((runs[1] / "hashes.json").read_text(encoding="utf-8"))
        for entry in hashes["entries"]:
            entry["sha256"] = sha256_path(runs[1] / entry["path"])
        write_json(runs[1] / "hashes.json", hashes)
        result = validate_run_dir(runs[1])
        self.assertFalse(result["ok"])
        self.assertIn("differs from the fingerprint execution identity", "\n".join(result["errors"]))

    def test_a_receipt_that_drops_the_requirement_is_caught(self) -> None:
        runs, load = self.run_agent_pair(contained=False)
        forged = load("isolation_receipt.json")
        forged.update(isolation_required=False, required_reasons=[], status="not_required")
        forged["sha256"] = sha256_json({k: v for k, v in forged.items() if k != "sha256"})
        write_json(runs[1] / EVAL / "isolation_receipt.json", forged)
        hashes = json.loads((runs[1] / "hashes.json").read_text(encoding="utf-8"))
        for entry in hashes["entries"]:
            entry["sha256"] = sha256_path(runs[1] / entry["path"])
        write_json(runs[1] / "hashes.json", hashes)
        result = validate_run_dir(runs[1])
        self.assertFalse(result["ok"])
        self.assertIn("requirement differs from the manifest", "\n".join(result["errors"]))

    def test_a_deleted_receipt_is_caught(self) -> None:
        runs, _ = self.run_agent_pair(contained=True)
        (runs[1] / EVAL / "isolation_receipt.json").unlink()
        hashes = json.loads((runs[1] / "hashes.json").read_text(encoding="utf-8"))
        hashes["entries"] = [e for e in hashes["entries"] if not e["path"].endswith("isolation_receipt.json")]
        write_json(runs[1] / "hashes.json", hashes)
        result = validate_run_dir(runs[1])
        self.assertFalse(result["ok"])
        self.assertIn("isolation_receipt", "\n".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
