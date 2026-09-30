from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from era_cli.commands.run import execute_run
from era_core.eval_judge import (
    MAX_LISTED_DISAGREEMENTS,
    analyze_evidence,
    build_judge_audit,
    cohens_kappa,
    evaluate_audit,
    read_judge_evidence,
    thresholds_from,
    validate_judge_audit,
    validate_judge_policy,
)
from era_core.eval_lane import validate_eval_policy
from era_core.hashing import sha256_json, write_json
from era_core.validation import validate_run_dir
from tests.fixtures.eval.factories import make_fingerprint
from tests.test_artifact_generation import init_git_repo
from tests.test_eval_lane import EVALUATION, write_v2_manifest

JUDGE_POLICY = {
    "judge_metrics": ["helpfulness"],
    "judge_evidence_path": "judge/evidence.json",
    "min_items": 20,
    "min_position_consistency": 0.8,
    "min_calibration_items": 10,
    "min_human_agreement": 0.8,
    "require_family_separation": True,
}
THRESHOLDS = thresholds_from(JUDGE_POLICY)


def items(count=30, calibration=12, flips=0, human_wrong=0):
    result = []
    for index in range(count):
        entry = {"item_id": str(index), "winner_ab": "candidate", "winner_ba": "candidate"}
        if index < flips:
            entry["winner_ba"] = "baseline"
        if index >= count - calibration:
            entry["human_label"] = "candidate"
        result.append(entry)
    wrong = [e for e in result if "human_label" in e][:human_wrong]
    for entry in wrong:
        entry["human_label"] = "baseline"
    return result


def evidence(judge_family="family-a", subject_family="family-b", **kwargs):
    return {
        "schema_version": "JudgeEvidence.v1",
        "judge": {"model_family": judge_family, "model_id": "judge-1", "prompt_hash": "p1"},
        "subject": {"model_family": subject_family},
        "items": items(**kwargs),
    }


def audit_of(data, thresholds=THRESHOLDS):
    return build_judge_audit(
        fingerprint=make_fingerprint(),
        evidence=data,
        read_problems=[],
        thresholds=thresholds,
        judge_metrics=["helpfulness"],
        raw_evidence_refs=["judge_evidence:x"],
    )


class AnalysisTests(unittest.TestCase):
    def test_clean_evidence_passes(self) -> None:
        audit = audit_of(evidence())
        self.assertEqual(audit["audit_status"], "passed")
        self.assertEqual(audit["position_consistency"], 1.0)
        self.assertEqual(audit["human_agreement"], 1.0)
        self.assertEqual(audit["authority"], "evidence_only")
        self.assertEqual(validate_judge_audit(audit), [])

    def test_position_flips_are_measured_and_kept(self) -> None:
        analysis = analyze_evidence(evidence(flips=10))
        self.assertAlmostEqual(analysis["position_consistency"], 20 / 30, places=4)
        flips = [d for d in analysis["disagreements"] if d["kind"] == "position_flip"]
        self.assertEqual(len(flips), 10)
        self.assertEqual(flips[0]["winner_ab"], "candidate")
        self.assertEqual(flips[0]["winner_ba"], "baseline")
        status, reasons = evaluate_audit(analysis, THRESHOLDS)
        self.assertEqual(status, "failed")
        self.assertTrue(any("Position consistency" in r for r in reasons))

    def test_human_disagreements_are_kept(self) -> None:
        analysis = analyze_evidence(evidence(human_wrong=4))
        self.assertAlmostEqual(analysis["human_agreement"], 8 / 12, places=4)
        self.assertEqual(len([d for d in analysis["disagreements"] if d["kind"] == "human_disagreement"]), 4)
        self.assertEqual(evaluate_audit(analysis, THRESHOLDS)[0], "failed")

    def test_an_inconsistent_calibration_item_counts_against_agreement(self) -> None:
        data = evidence(count=30, calibration=12, flips=0)
        calibrated = [i for i in data["items"] if "human_label" in i]
        calibrated[0]["winner_ba"] = "baseline"
        analysis = analyze_evidence(data)
        self.assertAlmostEqual(analysis["human_agreement"], 11 / 12, places=4)
        self.assertEqual(analysis["counts"]["consistent_items"], 29)

    def test_unpaired_items_are_excluded_from_rates_but_listed(self) -> None:
        data = evidence()
        del data["items"][0]["winner_ba"]
        data["items"].append({"winner_ab": "candidate"})
        analysis = analyze_evidence(data)
        self.assertEqual(analysis["counts"]["unpaired_items"], 2)
        self.assertEqual(analysis["counts"]["paired_items"], 29)
        kinds = {d["kind"] for d in analysis["disagreements"]}
        self.assertEqual(kinds, {"unpaired_order", "malformed_item"})

    def test_family_separation(self) -> None:
        same = audit_of(evidence(judge_family="family-a", subject_family="family-a"))
        self.assertEqual(same["audit_status"], "failed")
        self.assertIn("share the model family", " ".join(same["failure_reasons"]))
        unknown = audit_of(evidence(subject_family=None))
        self.assertEqual(unknown["audit_status"], "unproven")
        relaxed = audit_of(evidence(judge_family="family-a", subject_family="family-a"), {**THRESHOLDS, "require_family_separation": False})
        self.assertEqual(relaxed["audit_status"], "passed")

    def test_thin_evidence_is_unproven_not_passed(self) -> None:
        few_items = audit_of(evidence(count=10, calibration=10))
        self.assertEqual(few_items["audit_status"], "unproven")
        few_labels = audit_of(evidence(count=30, calibration=3))
        self.assertEqual(few_labels["audit_status"], "unproven")
        self.assertIn("human-labelled", " ".join(few_labels["failure_reasons"]))

    def test_failure_outranks_unproven(self) -> None:
        audit = audit_of(evidence(count=30, calibration=3, judge_family="x", subject_family="x"))
        self.assertEqual(audit["audit_status"], "failed")

    def test_disagreement_list_is_capped_but_total_is_kept(self) -> None:
        audit = audit_of(evidence(count=200, calibration=12, flips=120))
        self.assertEqual(audit["disagreement_total"], 120)
        self.assertEqual(len(audit["disagreements"]), MAX_LISTED_DISAGREEMENTS)
        self.assertTrue(audit["disagreements_truncated"])

    def test_kappa(self) -> None:
        self.assertEqual(cohens_kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")]), 1.0)
        self.assertLess(cohens_kappa([("a", "b"), ("b", "a"), ("a", "a"), ("b", "b")]), 0.1)
        self.assertIsNone(cohens_kappa([("a", "a"), ("a", "a")]))
        self.assertIsNone(cohens_kappa([]))


class ReadAndPolicyTests(unittest.TestCase):
    def test_read_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "judge").mkdir()
            path = root / "judge" / "evidence.json"
            path.write_text(json.dumps(evidence()), encoding="utf-8")
            data, digest, problems = read_judge_evidence(root, ".", "judge/evidence.json")
            self.assertEqual((problems, bool(digest)), ([], True))
            self.assertIn("escapes", read_judge_evidence(root, ".", "../x")[2][0])
            self.assertIn("does not exist", read_judge_evidence(root, ".", "judge/none.json")[2][0])
            path.write_text("x", encoding="utf-8")
            self.assertIn("not valid JSON", read_judge_evidence(root, ".", "judge/evidence.json")[2][0])
            path.write_text(json.dumps({"schema_version": "Other"}), encoding="utf-8")
            self.assertIn("is not JudgeEvidence.v1", read_judge_evidence(root, ".", "judge/evidence.json")[2][0])
            path.write_text(json.dumps({"schema_version": "JudgeEvidence.v1"}), encoding="utf-8")
            self.assertIn("needs judge and items", read_judge_evidence(root, ".", "judge/evidence.json")[2][0])

    def test_unreadable_evidence_is_an_invalid_audit(self) -> None:
        audit = build_judge_audit(
            fingerprint=make_fingerprint(), evidence=None, read_problems=["gone"], thresholds=THRESHOLDS,
            judge_metrics=["helpfulness"], raw_evidence_refs=[],
        )
        self.assertEqual((audit["audit_status"], audit["failure_reasons"]), ("invalid", ["gone"]))
        self.assertEqual(validate_judge_audit(audit), [])

    def test_policy_validation(self) -> None:
        self.assertEqual(validate_judge_policy(JUDGE_POLICY), [])
        for bad in (
            {**JUDGE_POLICY, "judge_metrics": []},
            {**JUDGE_POLICY, "judge_evidence_path": ""},
            {**JUDGE_POLICY, "min_items": 0},
            {**JUDGE_POLICY, "min_human_agreement": 1.5},
            {**JUDGE_POLICY, "require_family_separation": "yes"},
            "x",
        ):
            self.assertTrue(validate_judge_policy(bad), bad)

    def test_every_judge_metric_needs_a_floor(self) -> None:
        policy = copy.deepcopy(EVALUATION)
        policy["quality_gate_policy"]["judge_policy"] = copy.deepcopy(JUDGE_POLICY)
        self.assertTrue(any("no quality floor" in e for e in validate_eval_policy(policy)))
        policy["quality_gate_policy"]["quality_floors"]["helpfulness"] = {"min": 0.7}
        self.assertEqual(validate_eval_policy(policy), [])


class AuditValidationTests(unittest.TestCase):
    def test_forged_status_fails_even_when_resealed(self) -> None:
        audit = audit_of(evidence(flips=15))
        self.assertEqual(audit["audit_status"], "failed")
        audit.update(audit_status="passed", failure_reasons=[])
        audit["sha256"] = sha256_json({k: v for k, v in audit.items() if k != "sha256"})
        self.assertTrue(any("contradicts its numbers" in e for e in validate_judge_audit(audit)))

    def test_authority_must_stay_evidence_only(self) -> None:
        audit = audit_of(evidence())
        audit["authority"] = "canonical"
        audit["sha256"] = sha256_json({k: v for k, v in audit.items() if k != "sha256"})
        self.assertTrue(any("never canonical truth" in e for e in validate_judge_audit(audit)))

    def test_tamper_and_missing_fields(self) -> None:
        audit = audit_of(evidence())
        tampered = {**audit, "position_consistency": 0.1}
        self.assertTrue(any("sha256 mismatch" in e for e in validate_judge_audit(tampered)))
        del audit["thresholds"]
        self.assertTrue(validate_judge_audit(audit))


JUDGE_EVAL = copy.deepcopy(EVALUATION)
JUDGE_EVAL["quality_gate_policy"] = {
    "quality_floors": {"accuracy": {"min": 0.9}, "helpfulness": {"min": 0.7}},
    "quality_results_path": "quality/results.json",
    "judge_policy": copy.deepcopy(JUDGE_POLICY),
}
EVAL = "evidence/efficiency/eval/eval_probe"


class EndToEndJudgeTests(unittest.TestCase):
    def make(self, data, helpfulness=0.9, accuracy=0.95):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        (repo / "quality").mkdir()
        (repo / "quality" / "results.json").write_text(
            json.dumps({"metric_results": {"accuracy": accuracy, "helpfulness": helpfulness}, "sample_count": 30}),
            encoding="utf-8",
        )
        if data is not None:
            (repo / "judge").mkdir()
            (repo / "judge" / "evidence.json").write_text(json.dumps(data), encoding="utf-8")
        write_v2_manifest(era_root, repo.name, copy.deepcopy(JUDGE_EVAL))
        run_dir = execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=era_root / "artifacts" / "era-runs")
        load = lambda name: json.loads((run_dir / EVAL / name).read_text(encoding="utf-8"))  # noqa: E731
        return run_dir, load

    def test_passed_audit_admits_the_judge_metric(self) -> None:
        run_dir, load = self.make(evidence())
        self.assertEqual(load("judge_audit.json")["audit_status"], "passed")
        gate = load("quality_gate.json")
        self.assertEqual(gate["gate_status"], "passed")
        self.assertIn("helpfulness", gate["metric_results"])
        self.assertEqual(load("judge_audit.json")["config_fingerprint_sha256"], load("fingerprint.json")["sha256"])
        result = validate_run_dir(run_dir)
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))
        review = (run_dir / "review.md").read_text(encoding="utf-8")
        for text in (
            "judge audit: `passed` (evidence only, never canonical truth)",
            "judge family `family-a`, subject family `family-b`",
            "position consistency `1.0`",
            "disagreements kept: `0`",
            load("judge_audit.json")["sha256"],
        ):
            self.assertIn(text, review)

    def test_failed_audit_keeps_the_judge_metric_out_and_the_gate_unproven(self) -> None:
        run_dir, load = self.make(evidence(flips=15), helpfulness=0.99)
        self.assertEqual(load("judge_audit.json")["audit_status"], "failed")
        gate = load("quality_gate.json")
        self.assertNotIn("helpfulness", gate["metric_results"])
        self.assertEqual(gate["gate_status"], "unproven")
        self.assertIn("not admitted", " ".join(gate["failure_reasons"]))
        self.assertEqual(load("comparison.json")["claim_status"], "quality_unproven")
        review = (run_dir / "review.md").read_text(encoding="utf-8")
        self.assertIn("judge metrics not admitted to the quality gate: `helpfulness`", review)
        self.assertIn("disagreement `", review)
        result = validate_run_dir(run_dir)
        self.assertTrue(result["ok"], msg="\n".join(result["errors"]))

    def test_a_hard_quality_failure_still_wins_over_an_unadmitted_judge(self) -> None:
        _, load = self.make(evidence(flips=15), accuracy=0.2)
        self.assertEqual(load("quality_gate.json")["gate_status"], "failed")
        self.assertEqual(load("comparison.json")["claim_status"], "quality_blocked")

    def test_a_good_judge_score_cannot_offset_a_failed_hard_floor(self) -> None:
        _, load = self.make(evidence(), helpfulness=1.0, accuracy=0.2)
        self.assertEqual(load("comparison.json")["claim_status"], "quality_blocked")

    def test_a_low_admitted_judge_score_fails_the_gate(self) -> None:
        _, load = self.make(evidence(), helpfulness=0.3)
        self.assertEqual(load("quality_gate.json")["gate_status"], "failed")

    def test_missing_judge_evidence_is_an_invalid_audit_and_unproven_quality(self) -> None:
        _, load = self.make(None)
        self.assertEqual(load("judge_audit.json")["audit_status"], "invalid")
        self.assertEqual(load("quality_gate.json")["gate_status"], "unproven")

    def test_same_family_judge_is_failed(self) -> None:
        _, load = self.make(evidence(judge_family="fam", subject_family="fam"))
        self.assertEqual(load("judge_audit.json")["audit_status"], "failed")
        self.assertEqual(load("comparison.json")["claim_status"], "quality_unproven")

    def test_forging_the_audit_to_admit_a_judge_metric_is_caught(self) -> None:
        run_dir, load = self.make(evidence(flips=15), helpfulness=0.99)
        audit = load("judge_audit.json")
        audit.update(audit_status="passed", failure_reasons=[])
        audit["sha256"] = sha256_json({k: v for k, v in audit.items() if k != "sha256"})
        write_json(run_dir / EVAL / "judge_audit.json", audit)
        hashes = json.loads((run_dir / "hashes.json").read_text(encoding="utf-8"))
        for entry in hashes["entries"]:
            from era_core.hashing import sha256_path

            entry["sha256"] = sha256_path(run_dir / entry["path"])
        write_json(run_dir / "hashes.json", hashes)
        result = validate_run_dir(run_dir)
        self.assertFalse(result["ok"])

    def test_deleting_the_judge_audit_fails_validation(self) -> None:
        run_dir, _ = self.make(evidence())
        (run_dir / EVAL / "judge_audit.json").unlink()
        hashes = json.loads((run_dir / "hashes.json").read_text(encoding="utf-8"))
        hashes["entries"] = [e for e in hashes["entries"] if not e["path"].endswith("judge_audit.json")]
        write_json(run_dir / "hashes.json", hashes)
        result = validate_run_dir(run_dir)
        self.assertFalse(result["ok"])
        self.assertIn("judge_audit", "\n".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
