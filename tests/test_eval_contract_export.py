"""ERA's producer side of era_evaluation_export against the contract (forge_contract_core, RFC-ERA-EVAL-01)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from era_core.eval_contract_export import (
    ProjectionError,
    canonical_decimal,
    payload_digest,
    to_contract_payload,
)

VECTOR = Path(__file__).parent / "fixtures" / "eval" / "era_evaluation_export.decimal.vector.json"
ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "eval_proving_run.py"


def _contract_core():
    """Import the contract-core validator when a checkout is reachable. Otherwise return None."""
    try:
        from forge_contract_core.validators.artifact import validate_artifact

        return validate_artifact
    except ImportError:
        pass
    for candidate in (
        os.environ.get("FORGE_CONTRACT_CORE_PATH"),
        str(ROOT.parent / "contracts" / "forge_contract_core"),
        str(ROOT.parent / "forge_contract_core"),
    ):
        if candidate and (Path(candidate) / "forge_contract_core").is_dir():
            sys.path.insert(0, candidate)
            try:
                from forge_contract_core.validators.artifact import validate_artifact

                return validate_artifact
            except ImportError:
                sys.path.remove(candidate)
    return None


class DecimalParityTests(unittest.TestCase):
    """ERA's serializer agrees with the contract's own decimal vector (a copy, with provenance in the file)."""

    def test_every_vector_case(self) -> None:
        cases = json.loads(VECTOR.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 50)
        for case in cases:
            with self.subTest(input=case["input"]):
                if case["expected"] is None:
                    with self.assertRaises(ProjectionError):
                        canonical_decimal(case["input"])
                else:
                    self.assertEqual(canonical_decimal(case["input"]), case["expected"])

    def test_floats_ints_and_rejections(self) -> None:
        self.assertEqual(canonical_decimal(16.0), "16")
        self.assertEqual(canonical_decimal(-0.0), "0")
        self.assertEqual(canonical_decimal(1e-05), "0.00001")
        self.assertEqual(canonical_decimal(0.30000000000000004), "0.30000000000000004")
        for bad in (float("nan"), float("inf"), True, None, [], "abc"):
            with self.assertRaises(ProjectionError):
                canonical_decimal(bad)


class ProjectionTests(unittest.TestCase):
    def summary(self, **workload):
        base = {
            "workload_id": "w1", "subject_kind": "repository_command", "fingerprint_id": "fp", "config_digest": "0" * 64,
            "claim_status": "no_baseline", "quality_status": "passed", "comparability_status": "unknown",
            "efficiency_status": "not_evaluated", "isolation_status": "not_required", "judge_audit_status": None,
            "primary_metric": "median_ms", "measurement_scope": "wall_clock_internal_timer",
            "metrics": {"median_ms": {"value": 16.0, "unit": "ms", "direction": "lower_is_better"}},
            "metric_deltas": {}, "blocked_reasons": ["No prior run."], "baseline_rejection_reasons": [],
            "baseline_run_id": None, "baseline_fingerprint_id": None, "baseline": None, "artifacts": {},
        }
        base.update(workload)
        return {
            "run_id": "r1", "repo_id": "repo", "commit_sha": "a" * 40, "run_status": "completed",
            "efficiency_lane_classification": "unproven",
            "execution_posture": {"sandbox": "none", "sandbox_backend": "none", "network": "host",
                                  "target_filesystem": "writable", "target_trust": "operator_trusted",
                                  "attested_by": "someone", "executes_target_code": True},
            "workloads": [base], "created_at": "2026-09-30T00:00:00Z",
        }

    def test_projection_sorts_and_drops_identity(self) -> None:
        summary = self.summary()
        second = dict(summary["workloads"][0], workload_id="a0")
        summary["workloads"].append(second)
        payload = to_contract_payload(summary)
        self.assertEqual([w["workload_id"] for w in payload["workloads"]], ["a0", "w1"])
        self.assertNotIn("attested_by", payload["execution_posture"])
        self.assertEqual(payload["workloads"][1]["metrics"]["median_ms"], {"value": "16", "unit": "ms", "direction": "lower_is_better", "aggregation": "median"})

    def test_rejection_set_is_sorted_and_unique(self) -> None:
        payload = to_contract_payload(self.summary(baseline_rejection_reasons=["quality_failed", "evidence_invalid", "quality_failed"]))
        self.assertEqual(payload["workloads"][0]["baseline_rejection_reasons"], ["evidence_invalid", "quality_failed"])

    def test_duplicate_or_oversize_workload_ids_are_refused(self) -> None:
        summary = self.summary()
        summary["workloads"].append(dict(summary["workloads"][0]))
        with self.assertRaises(ProjectionError):
            to_contract_payload(summary)
        with self.assertRaises(ProjectionError):
            to_contract_payload(self.summary(workload_id="x" * 129))

    def test_long_reasons_are_bounded_and_counted(self) -> None:
        payload = to_contract_payload(self.summary(claim_status="evidence_blocked", blocked_reasons=["r" * 2000] + [f"n{i}" for i in range(80)]))
        reasons = payload["workloads"][0]["blocked_reasons"]
        self.assertEqual(len(reasons), 64)
        self.assertTrue(all(len(text) <= 1024 for text in reasons))
        self.assertTrue(reasons[0].endswith("..."))
        self.assertIn("more reasons were omitted", reasons[-1])

    def test_digest_excludes_only_itself_and_refuses_floats(self) -> None:
        payload = to_contract_payload(self.summary())
        self.assertEqual(payload_digest(payload), payload["payload_digest"])
        payload["payload_digest"] = "sha256:" + "0" * 64
        self.assertEqual(payload_digest(payload), to_contract_payload(self.summary())["payload_digest"])
        payload["run_id"] = "other"
        self.assertNotEqual(payload_digest(payload), to_contract_payload(self.summary())["payload_digest"])
        with self.assertRaises(ProjectionError):
            payload_digest({"x": 1.5})


@unittest.skipIf(_contract_core() is None, "forge_contract_core is not reachable (set FORGE_CONTRACT_CORE_PATH)")
class ContractConformanceTests(unittest.TestCase):
    """Every export from ERA's own proving run passes the contract's validator, with strict idempotency."""

    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("eval_proving_run", SCRIPT)
        cls.proving = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.proving)
        cls.temp = tempfile.TemporaryDirectory()
        cls.workdir = Path(cls.temp.name)
        cls.receipt = cls.proving.run_proving(cls.workdir)
        cls.runs = cls.workdir / "era" / "artifacts" / "era-runs"
        cls.validate = staticmethod(_contract_core())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_every_proving_scenario_export_is_a_valid_admitted_artifact(self) -> None:
        self.assertTrue(self.receipt["gate_06_pass"])
        for item in self.receipt["scenarios"]:
            with self.subTest(scenario=item["scenario"]):
                artifact = json.loads((self.runs / item["run_id"] / "evaluation_export.json").read_text(encoding="utf-8"))
                self.validate(artifact, strict_idempotency=True)

    def test_the_role_matrix_admits_era_as_producer_only(self) -> None:
        from forge_contract_core.validators.role_matrix import RoleMatrixViolationError, check_producer_admitted

        check_producer_admitted("ERA", "era_evaluation_export")
        with self.assertRaises(RoleMatrixViolationError):
            check_producer_admitted("dataforge-Local", "era_evaluation_export")

    def test_ERA_digest_equals_the_contract_digest(self) -> None:
        from forge_contract_core.validators.era_evaluation import era_export_digest

        for item in self.receipt["scenarios"]:
            artifact = json.loads((self.runs / item["run_id"] / "evaluation_export.json").read_text(encoding="utf-8"))
            self.assertEqual(era_export_digest(artifact["payload"]), artifact["payload"]["payload_digest"])

    def test_a_tampered_export_fails_the_contract_validator(self) -> None:
        from forge_contract_core.validators.artifact import ArtifactValidationError

        item = self.receipt["scenarios"][1]
        artifact = json.loads((self.runs / item["run_id"] / "evaluation_export.json").read_text(encoding="utf-8"))
        artifact["payload"]["workloads"][0]["claim_status"] = "promoted"
        with self.assertRaises(ArtifactValidationError):
            self.validate(artifact, strict_idempotency=True)


if __name__ == "__main__":
    unittest.main()
