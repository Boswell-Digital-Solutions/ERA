from __future__ import annotations

import copy
import unittest

from era_core.eval_snapshot import build_baseline_snapshot, validate_baseline_snapshot
from era_core.hashing import sha256_json
from tests.fixtures.eval.factories import make_fingerprint
from tests.test_eval_claims import as_prior, evidence


def reseal(payload):
    payload["sha256"] = sha256_json({k: v for k, v in payload.items() if k != "sha256"})
    return payload


def snapshot():
    return build_baseline_snapshot(
        candidate_fingerprint=make_fingerprint(run_id="run-c"), baseline=as_prior(evidence("run-b", 100))
    )


class SnapshotTests(unittest.TestCase):
    def test_valid_snapshot(self) -> None:
        data = snapshot()
        self.assertEqual(validate_baseline_snapshot(data), [])
        self.assertEqual(data["baseline_run_id"], "run-b")
        self.assertEqual(data["baseline_quality_status"], "passed")
        self.assertEqual(set(data["part_hashes"]), {"fingerprint", "quality_gate", "metric_vector"})

    def test_tamper_is_caught(self) -> None:
        data = snapshot()
        data["baseline_run_id"] = "other"
        self.assertTrue(any("sha256 mismatch" in e for e in validate_baseline_snapshot(data)))

    def test_a_resealed_snapshot_with_edited_evidence_is_caught(self) -> None:
        data = snapshot()
        data["metric_vector"]["metrics"]["median_ms"]["value"] = 1.0
        errors = validate_baseline_snapshot(reseal(data))
        self.assertTrue(any("metric vector" in e for e in errors))

    def test_mismatched_summary_fields_are_caught(self) -> None:
        for field, value, needle in (
            ("baseline_fingerprint_id", "x", "baseline_fingerprint_id"),
            ("baseline_config_digest", "x", "baseline_config_digest"),
            ("baseline_run_id", "x", "baseline_run_id"),
            ("baseline_quality_status", "failed", "baseline_quality_status"),
        ):
            data = snapshot()
            data[field] = value
            errors = validate_baseline_snapshot(reseal(data))
            self.assertTrue(any(needle in e for e in errors), field)

    def test_part_hash_must_match_the_copied_artifact(self) -> None:
        data = snapshot()
        data["part_hashes"] = {**data["part_hashes"], "quality_gate": "0" * 64}
        self.assertTrue(any("part hash for quality_gate" in e for e in validate_baseline_snapshot(reseal(data))))

    def test_missing_parts_and_wrong_schema(self) -> None:
        data = snapshot()
        del data["fingerprint"]
        self.assertTrue(validate_baseline_snapshot(data))
        self.assertTrue(validate_baseline_snapshot({**copy.deepcopy(snapshot()), "schema_version": "x"}))


if __name__ == "__main__":
    unittest.main()
