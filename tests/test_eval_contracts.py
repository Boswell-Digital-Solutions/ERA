from __future__ import annotations

import copy
import unittest

from era_core.eval_contracts import (
    build_metric_vector,
    build_quality_efficiency_comparison,
    build_quality_gate_artifact,
    check_evidence_linkage,
    evaluate_quality_floors,
    validate_config_fingerprint,
    validate_metric_vector,
    validate_quality_efficiency_comparison,
    validate_quality_gate_artifact,
)
from era_core.hashing import sha256_json
from tests.fixtures.eval.factories import FIXED_TIME, make_fingerprint

FLOORS = {"accuracy": {"min": 0.9}}


def make_gate(fingerprint, accuracy=0.95, samples=10):
    return build_quality_gate_artifact(
        fingerprint=fingerprint,
        metric_results={"accuracy": accuracy},
        quality_floors=FLOORS,
        sample_count=samples,
        raw_evidence_refs=["raw:1"],
        created_at=FIXED_TIME,
    )


def make_vector(fingerprint):
    return build_metric_vector(
        fingerprint=fingerprint,
        metrics={"median_ms": {"value": 120.0, "unit": "ms", "direction": "lower_is_better"}},
        sample_count=3,
        variance_or_uncertainty={"variance_classification": "stable"},
        measurement_scope="wall_clock",
        raw_evidence_refs=["raw:1"],
        created_at=FIXED_TIME,
    )


def make_comparison(**overrides):
    kwargs = {
        "run_id": "run-b",
        "workload_id": "w",
        "candidate_fingerprint_id": "fp-b",
        "baseline_fingerprint_id": "fp-a",
        "candidate_run_id": "run-b",
        "baseline_run_id": "run-a",
        "quality_status": "passed",
        "comparability_status": "comparable",
        "efficiency_status": "improvement",
        "claim_status": "permitted",
        "comparison_dimensions": {},
        "metric_deltas": {"median_ms": -20.0},
        "blocked_reasons": [],
        "created_at": FIXED_TIME,
    }
    kwargs.update(overrides)
    return build_quality_efficiency_comparison(**kwargs)


def tamper(payload, **changes):
    """Change fields without resealing, so the stored sha256 goes stale."""
    result = copy.deepcopy(payload)
    result.update(changes)
    return result


class FingerprintTests(unittest.TestCase):
    def test_valid_fingerprint_validates(self) -> None:
        self.assertEqual(validate_config_fingerprint(make_fingerprint()), [])

    def test_identical_config_gives_same_digest_across_runs(self) -> None:  # P05
        first = make_fingerprint(run_id="run-a")
        second = make_fingerprint(run_id="run-b", created_at="2026-10-01T00:00:00Z")
        self.assertEqual(first["config_digest"], second["config_digest"])
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_changed_config_changes_digest(self) -> None:
        self.assertNotEqual(
            make_fingerprint()["config_digest"],
            make_fingerprint(**{"subject_identity.quantization": "q4"})["config_digest"],
        )

    def test_tampered_fingerprint_fails(self) -> None:  # N14
        errors = validate_config_fingerprint(tamper(make_fingerprint(), repo_id="other"))
        self.assertTrue(any("stale or tampered" in item for item in errors))
        self.assertTrue(any("sha256 mismatch" in item for item in errors))

    def test_stale_digest_fails_even_when_resealed(self) -> None:
        payload = make_fingerprint()
        payload["subject_identity"] = {"model_id": "swapped"}
        payload["sha256"] = sha256_json({k: v for k, v in payload.items() if k != "sha256"})
        self.assertTrue(any("config_digest" in item for item in validate_config_fingerprint(payload)))

    def test_missing_evaluation_field_and_bad_kind_fail(self) -> None:
        payload = make_fingerprint()
        del payload["evaluation_identity"]["scorer_version"]
        payload["subject_kind"] = "oracle"
        errors = validate_config_fingerprint(payload)
        self.assertTrue(any("scorer_version" in item for item in errors))
        self.assertTrue(any("subject_kind" in item for item in errors))

    def test_wrong_schema_version_fails(self) -> None:
        self.assertTrue(validate_config_fingerprint(tamper(make_fingerprint(), schema_version="x")))


class QualityGateTests(unittest.TestCase):
    def test_passed_gate_validates(self) -> None:
        gate = make_gate(make_fingerprint())
        self.assertEqual(gate["gate_status"], "passed")
        self.assertEqual(validate_quality_gate_artifact(gate), [])

    def test_floor_evaluation(self) -> None:
        self.assertEqual(evaluate_quality_floors({"a": 0.5}, {"a": {"min": 0.9}}, 5)[0], "failed")
        self.assertEqual(evaluate_quality_floors({}, {"a": {"min": 0.9}}, 5)[0], "unproven")
        self.assertEqual(evaluate_quality_floors({"a": 1}, {}, 5)[0], "unproven")
        self.assertEqual(evaluate_quality_floors({"a": 1}, {"a": {"min": 0.9}}, 0)[0], "unproven")
        self.assertEqual(evaluate_quality_floors({"a": True}, {"a": {"min": 0.9}}, 5)[0], "unproven")
        self.assertEqual(evaluate_quality_floors({"a": 1}, {"a": {"min": 1, "max": 2}}, 5)[0], "invalid")
        self.assertEqual(evaluate_quality_floors({"a": 3}, {"a": {"max": 2}}, 5)[0], "failed")
        self.assertEqual(evaluate_quality_floors({"a": 2}, {"a": {"equals": 2}}, 5)[0], "passed")

    def test_partial_evidence_is_never_passed(self) -> None:
        status, _ = evaluate_quality_floors({"a": 1}, {"a": {"min": 0}, "b": {"min": 0}}, 5)
        self.assertEqual(status, "unproven")

    def test_failed_and_unproven_gates_validate_with_reasons(self) -> None:
        failed = make_gate(make_fingerprint(), accuracy=0.5)
        unproven = make_gate(make_fingerprint(), samples=0)
        self.assertEqual(failed["gate_status"], "failed")
        self.assertEqual(unproven["gate_status"], "unproven")
        self.assertEqual(validate_quality_gate_artifact(failed), [])
        self.assertEqual(validate_quality_gate_artifact(unproven), [])

    def test_forged_passed_status_fails_validation(self) -> None:
        failed = make_gate(make_fingerprint(), accuracy=0.5)
        forged = tamper(failed, gate_status="passed", failure_reasons=[])
        forged["sha256"] = sha256_json({k: v for k, v in forged.items() if k != "sha256"})
        self.assertTrue(any("contradicts its floors" in item for item in validate_quality_gate_artifact(forged)))

    def test_tampered_quality_artifact_fails(self) -> None:  # N13
        errors = validate_quality_gate_artifact(tamper(make_gate(make_fingerprint()), sample_count=99))
        self.assertTrue(any("sha256 mismatch" in item for item in errors))

    def test_missing_field_fails(self) -> None:
        gate = make_gate(make_fingerprint())
        del gate["suite_id"]
        self.assertTrue(any("suite_id" in item for item in validate_quality_gate_artifact(gate)))


class MetricVectorTests(unittest.TestCase):
    def test_valid_vector_validates(self) -> None:
        self.assertEqual(validate_metric_vector(make_vector(make_fingerprint())), [])

    def test_missing_direction_fails(self) -> None:  # N16
        vector = make_vector(make_fingerprint())
        del vector["metrics"]["median_ms"]["direction"]
        self.assertTrue(any("direction" in item for item in validate_metric_vector(vector)))

    def test_non_numeric_and_empty_metrics_fail(self) -> None:
        fingerprint = make_fingerprint()
        vector = build_metric_vector(
            fingerprint=fingerprint,
            metrics={"m": {"value": "fast", "direction": "lower_is_better"}},
            sample_count=1,
            variance_or_uncertainty={},
            measurement_scope="s",
            raw_evidence_refs=[],
            created_at=FIXED_TIME,
        )
        self.assertTrue(any("numeric" in item for item in validate_metric_vector(vector)))
        vector["metrics"] = {}
        self.assertTrue(any("at least one metric" in item for item in validate_metric_vector(vector)))


class ComparisonTests(unittest.TestCase):
    def test_permitted_improvement_validates(self) -> None:
        self.assertEqual(validate_quality_efficiency_comparison(make_comparison()), [])

    def test_improvement_without_quality_pass_fails(self) -> None:
        for status in ("failed", "unproven", "invalid"):
            comparison = make_comparison(quality_status=status)
            self.assertTrue(validate_quality_efficiency_comparison(comparison), status)

    def test_improvement_without_comparable_baseline_fails(self) -> None:
        for status in ("incomparable", "unknown"):
            self.assertTrue(validate_quality_efficiency_comparison(make_comparison(comparability_status=status)))
        self.assertTrue(validate_quality_efficiency_comparison(make_comparison(baseline_fingerprint_id=None)))

    def test_direction_claim_needs_permitted(self) -> None:
        comparison = make_comparison(claim_status="evidence_blocked", blocked_reasons=["x"])
        self.assertTrue(validate_quality_efficiency_comparison(comparison))

    def test_blocked_outcomes_validate(self) -> None:  # N01, N02, N03
        cases = [
            {"quality_status": "failed", "claim_status": "quality_blocked", "efficiency_status": "not_evaluated"},
            {"quality_status": "unproven", "claim_status": "quality_unproven", "efficiency_status": "not_evaluated"},
            {"comparability_status": "incomparable", "claim_status": "incomparable", "efficiency_status": "not_evaluated"},
        ]
        for case in cases:
            comparison = make_comparison(blocked_reasons=["reason"], **case)
            self.assertEqual(validate_quality_efficiency_comparison(comparison), [], case)

    def test_blocked_claim_needs_reason_and_matching_status(self) -> None:
        self.assertTrue(
            validate_quality_efficiency_comparison(
                make_comparison(quality_status="failed", claim_status="quality_blocked", efficiency_status="not_evaluated")
            )
        )
        self.assertTrue(
            validate_quality_efficiency_comparison(
                make_comparison(
                    quality_status="passed",
                    claim_status="quality_blocked",
                    efficiency_status="not_evaluated",
                    blocked_reasons=["x"],
                )
            )
        )

    def test_unstable_needs_its_own_claim_status(self) -> None:  # operator ruling 1
        ok = make_comparison(efficiency_status="unstable", claim_status="no_claim_unstable", blocked_reasons=["noisy"])
        self.assertEqual(validate_quality_efficiency_comparison(ok), [])
        for status in ("permitted", "evidence_blocked"):
            bad = make_comparison(efficiency_status="unstable", claim_status=status, blocked_reasons=["x"])
            self.assertTrue(validate_quality_efficiency_comparison(bad), status)
        wrong = make_comparison(efficiency_status="within_range", claim_status="no_claim_unstable", blocked_reasons=["x"])
        self.assertTrue(validate_quality_efficiency_comparison(wrong))

    def test_no_claim_unstable_still_needs_passed_quality_and_baseline(self) -> None:
        bad = make_comparison(
            efficiency_status="unstable", claim_status="no_claim_unstable", quality_status="unproven", blocked_reasons=["x"]
        )
        self.assertTrue(validate_quality_efficiency_comparison(bad))

    def test_permitted_needs_a_direction_result(self) -> None:
        self.assertTrue(validate_quality_efficiency_comparison(make_comparison(efficiency_status="not_evaluated")))

    def test_no_baseline_is_a_valid_blocked_claim(self) -> None:
        comparison = make_comparison(
            baseline_fingerprint_id=None,
            baseline_run_id=None,
            comparability_status="unknown",
            efficiency_status="not_evaluated",
            claim_status="no_baseline",
            blocked_reasons=["No prior run."],
        )
        self.assertEqual(validate_quality_efficiency_comparison(comparison), [])

    def test_invalid_enum_and_tamper_fail(self) -> None:
        self.assertTrue(validate_quality_efficiency_comparison(make_comparison(claim_status="great")))
        errors = validate_quality_efficiency_comparison(tamper(make_comparison(), workload_id="other"))
        self.assertTrue(any("sha256 mismatch" in item for item in errors))


class LinkageTests(unittest.TestCase):
    def test_matching_artifacts_link(self) -> None:
        fingerprint = make_fingerprint()
        self.assertEqual(check_evidence_linkage(fingerprint, make_gate(fingerprint), make_vector(fingerprint)), [])

    def test_missing_quality_is_not_a_linkage_error(self) -> None:
        fingerprint = make_fingerprint()
        self.assertEqual(check_evidence_linkage(fingerprint, None, make_vector(fingerprint)), [])

    def test_quality_for_other_fingerprint_is_blocked(self) -> None:  # N11
        fingerprint = make_fingerprint()
        other = make_fingerprint(run_id="run-z")
        errors = check_evidence_linkage(fingerprint, make_gate(other), None)
        self.assertTrue(any("fingerprint id" in item for item in errors))

    def test_vector_for_other_fingerprint_is_blocked(self) -> None:  # N12
        fingerprint = make_fingerprint()
        other = make_fingerprint(**{"subject_identity.quantization": "q4"})
        self.assertTrue(check_evidence_linkage(fingerprint, None, make_vector(other)))

    def test_stale_digest_reference_is_blocked(self) -> None:
        fingerprint = make_fingerprint()
        gate = tamper(make_gate(fingerprint), config_fingerprint_sha256="0" * 64)
        self.assertTrue(any("digest" in item for item in check_evidence_linkage(fingerprint, gate, None)))


if __name__ == "__main__":
    unittest.main()
