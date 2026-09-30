from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from era_core.eval_reconstruct import compare_to_stored, reconstruct_claim
from era_core.hashing import sha256_json, write_json

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_proving_run.py"
spec = importlib.util.spec_from_file_location("eval_proving_run", SCRIPT)
proving = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proving)


class ProvingRunTests(unittest.TestCase):
    """GATE-06: every outcome is proven and rebuilt from artifacts, with no live dependency."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.workdir = Path(cls.temp.name)
        cls.receipt = proving.run_proving(cls.workdir)
        cls.by_name = {item["scenario"]: item for item in cls.receipt["scenarios"]}
        cls.runs = cls.workdir / "era" / "artifacts" / "era-runs"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_gate_06_passes(self) -> None:
        failed = [item for item in self.receipt["scenarios"] if not item["passed"]]
        self.assertEqual(failed, [], msg=json.dumps(failed, indent=2))
        self.assertTrue(self.receipt["gate_06_pass"])

    def test_receipt_is_sealed_and_names_no_live_dependency(self) -> None:
        body = {k: v for k, v in self.receipt.items() if k != "sha256"}
        self.assertEqual(self.receipt["sha256"], sha256_json(body))
        self.assertEqual(
            self.receipt["live_dependencies"],
            {"model_calls": 0, "provider_calls": 0, "agent_runs": 0, "network": "not used"},
        )

    def test_all_five_required_outcomes_and_regression_are_present(self) -> None:
        claims = {name: item["actual"]["claim"] for name, item in self.by_name.items()}
        self.assertEqual(
            claims,
            {
                "baseline": "no_baseline",
                "allowed_improvement": "permitted",
                "allowed_regression": "permitted",
                "quality_blocked_faster_candidate": "quality_blocked",
                "quality_unproven_candidate": "quality_unproven",
                "incomparable_config": "incomparable",
                "unstable_measurement": "no_claim_unstable",
            },
        )
        self.assertEqual(self.by_name["allowed_improvement"]["actual"]["efficiency"], "improvement")
        self.assertEqual(self.by_name["allowed_regression"]["actual"]["efficiency"], "regression")

    def test_only_the_permitted_regression_makes_a_finding(self) -> None:
        counts = {name: item["actual"]["findings"] for name, item in self.by_name.items()}
        self.assertEqual(sum(counts.values()), 1)
        self.assertEqual(counts["allowed_regression"], 1)

    def test_blocked_outcomes_keep_their_reasons(self) -> None:
        for name in ("quality_blocked_faster_candidate", "quality_unproven_candidate", "incomparable_config", "unstable_measurement"):
            self.assertTrue(self.by_name[name]["blocked_reasons"], name)
        rejected = {r["reason"] for r in self.by_name["unstable_measurement"]["baseline_rejections"]}
        self.assertTrue({"quality_failed", "quality_unproven", "fingerprint_incomparable"} <= rejected)

    def test_reconstruction_ignores_later_runs(self) -> None:
        first = self.runs / self.by_name["baseline"]["run_id"]
        self.assertEqual(reconstruct_claim(first, proving.WORKLOAD_ID)["claim_status"], "no_baseline")
        self.assertTrue(compare_to_stored(first, proving.WORKLOAD_ID)["match"])

    def test_reconstruction_detects_a_changed_stored_claim(self) -> None:
        run_dir = self.runs / self.by_name["quality_blocked_faster_candidate"]["run_id"]
        path = run_dir / proving.EVAL / "comparison.json"
        original = path.read_text(encoding="utf-8")
        try:
            forged = json.loads(original)
            forged.update(claim_status="permitted", efficiency_status="improvement", quality_status="passed")
            forged["sha256"] = sha256_json({k: v for k, v in forged.items() if k != "sha256"})
            write_json(path, forged)
            result = compare_to_stored(run_dir, proving.WORKLOAD_ID)
            self.assertFalse(result["match"])
            self.assertTrue(any("claim_status" in item for item in result["differences"]))
        finally:
            path.write_text(original, encoding="utf-8")
        self.assertTrue(compare_to_stored(run_dir, proving.WORKLOAD_ID)["match"])

    def test_reconstruction_detects_a_changed_quality_gate(self) -> None:
        run_dir = self.runs / self.by_name["quality_blocked_faster_candidate"]["run_id"]
        path = run_dir / proving.EVAL / "quality_gate.json"
        original = path.read_text(encoding="utf-8")
        try:
            gate = json.loads(original)
            gate.update(gate_status="passed", failure_reasons=[], metric_results={"accuracy": 0.99})
            write_json(path, gate)
            self.assertFalse(compare_to_stored(run_dir, proving.WORKLOAD_ID)["match"])
        finally:
            path.write_text(original, encoding="utf-8")

    def test_missing_evidence_cannot_be_reconstructed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / "run"
            empty.mkdir()
            result = compare_to_stored(empty, proving.WORKLOAD_ID)
            self.assertFalse(result["match"])
            self.assertEqual(result["reconstructed"]["claim_status"], "evidence_blocked")


if __name__ == "__main__":
    unittest.main()
