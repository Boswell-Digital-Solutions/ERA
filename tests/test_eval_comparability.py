from __future__ import annotations

import unittest

from era_core.eval_comparability import (
    DEFAULT_REQUIRED_DIMENSIONS,
    compare_fingerprints,
    flatten_dimensions,
    is_known_dimension,
    select_baseline,
)
from tests.fixtures.eval.factories import make_fingerprint

SENSITIVE = DEFAULT_REQUIRED_DIMENSIONS + (
    "subject.model_revision",
    "subject.quantization",
    "runtime.prompt_template_hash",
    "evaluation.scorer_version",
    "evaluation.harness_version",
    "execution.hardware_fingerprint",
    "execution.concurrency",
    "execution.batch_size",
)


def status(candidate, baseline, required=SENSITIVE, waived=()):
    return compare_fingerprints(candidate, baseline, required, waived)["comparability_status"]


class CompareTests(unittest.TestCase):
    def test_identical_config_is_comparable_despite_different_runs(self) -> None:
        baseline = make_fingerprint(run_id="run-a")
        candidate = make_fingerprint(run_id="run-b", source_commit_sha="b" * 40)
        self.assertEqual(status(candidate, baseline), "comparable")

    def test_each_required_dimension_change_is_incomparable(self) -> None:  # N03-N09
        baseline = make_fingerprint()
        changes = {
            "subject_identity.model_revision": "rev2",
            "subject_identity.quantization": "q4",
            "runtime_identity.prompt_template_hash": "p2",
            "evaluation_identity.dataset_or_fixture_hash": "d2",
            "evaluation_identity.scorer_version": "2",
            "evaluation_identity.harness_version": "2",
            "evaluation_identity.quality_floor_policy_id": "floor-2",
            "execution_identity.hardware_fingerprint": "hw2",
            "execution_identity.concurrency": 8,
            "execution_identity.batch_size": 4,
            "subject_kind": "agent",
            "workload_id": "other_workload",
            "repo_id": "other_repo",
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                self.assertEqual(status(make_fingerprint(**{key: value}), baseline), "incomparable")

    def test_mismatch_reason_names_the_dimension(self) -> None:
        result = compare_fingerprints(
            make_fingerprint(**{"subject_identity.quantization": "q4"}),
            make_fingerprint(),
            SENSITIVE,
        )
        self.assertTrue(any("subject.quantization" in item for item in result["blocked_reasons"]))
        self.assertEqual(result["comparison_dimensions"]["subject.quantization"]["result"], "mismatch")

    def test_non_binding_dimension_is_waived_only_when_declared(self) -> None:
        candidate = make_fingerprint(**{"execution_identity.concurrency": 8})
        baseline = make_fingerprint()
        self.assertEqual(status(candidate, baseline), "incomparable")
        self.assertEqual(status(candidate, baseline, waived=("execution.concurrency",)), "comparable")

    def test_unrelated_dimension_change_does_not_block(self) -> None:
        candidate = make_fingerprint(**{"runtime_identity.engine_version": "2.0"})
        self.assertEqual(status(candidate, make_fingerprint(), DEFAULT_REQUIRED_DIMENSIONS), "comparable")

    def test_unknown_dimension_gives_unknown(self) -> None:  # N17
        self.assertEqual(status(make_fingerprint(), make_fingerprint(), ("vibes",)), "unknown")

    def test_missing_dimension_gives_unknown(self) -> None:
        baseline = make_fingerprint()
        del baseline["execution_identity"]["hardware_fingerprint"]
        self.assertEqual(status(make_fingerprint(), baseline, ("execution.hardware_fingerprint",)), "unknown")

    def test_mismatch_outranks_unknown(self) -> None:
        candidate = make_fingerprint(**{"subject_identity.quantization": "q4"})
        self.assertEqual(status(candidate, make_fingerprint(), ("vibes", "subject.quantization")), "incomparable")

    def test_empty_required_set_is_comparable_only_by_explicit_request(self) -> None:
        self.assertEqual(status(make_fingerprint(), make_fingerprint(repo_id="x"), ()), "comparable")

    def test_known_dimension_grammar(self) -> None:
        self.assertTrue(is_known_dimension("subject.anything"))
        self.assertTrue(is_known_dimension("execution.batch_size"))
        self.assertFalse(is_known_dimension("execution.color"))
        self.assertFalse(is_known_dimension("evaluation.nope"))
        self.assertFalse(is_known_dimension("subject."))
        self.assertFalse(is_known_dimension("nonsense"))

    def test_flatten_exposes_commit_and_groups(self) -> None:
        flat = flatten_dimensions(make_fingerprint())
        self.assertEqual(flat["source.commit_sha"], "a" * 40)
        self.assertEqual(flat["subject.quantization"], "q8")
        self.assertEqual(flat["evaluation.suite_id"], "suite")


class SelectBaselineTests(unittest.TestCase):
    def test_picks_latest_comparable_and_reports_rejections(self) -> None:
        candidate = make_fingerprint(run_id="run-c")
        old = make_fingerprint(run_id="run-1", created_at="2026-09-01T00:00:00Z")
        newer = make_fingerprint(run_id="run-2", created_at="2026-09-02T00:00:00Z")
        other_quant = make_fingerprint(
            run_id="run-3", created_at="2026-09-03T00:00:00Z", **{"subject_identity.quantization": "q4"}
        )
        result = select_baseline(candidate, [old, newer, other_quant], SENSITIVE)
        self.assertTrue(result["baseline_found"])
        self.assertEqual(result["baseline_run_id"], "run-2")
        self.assertEqual([item["run_id"] for item in result["rejected"]], ["run-3"])
        self.assertEqual(result["rejected"][0]["comparability_status"], "incomparable")

    def test_same_repo_and_workload_but_incomparable_is_no_baseline(self) -> None:  # N15
        candidate = make_fingerprint(run_id="run-c")
        prior = make_fingerprint(run_id="run-1", **{"evaluation_identity.dataset_or_fixture_hash": "d2"})
        result = select_baseline(candidate, [prior])
        self.assertFalse(result["baseline_found"])
        self.assertIsNone(result["baseline_run_id"])
        self.assertEqual(len(result["rejected"]), 1)

    def test_candidate_never_selects_itself(self) -> None:
        candidate = make_fingerprint(run_id="run-c")
        self.assertFalse(select_baseline(candidate, [candidate])["baseline_found"])

    def test_no_priors_is_no_baseline(self) -> None:
        self.assertFalse(select_baseline(make_fingerprint(), [])["baseline_found"])


if __name__ == "__main__":
    unittest.main()


class SameSecondOrderingTests(unittest.TestCase):
    def test_latest_is_the_one_created_last_even_within_one_second(self) -> None:
        from era_core.eval_contracts import build_config_fingerprint
        from tests.fixtures.eval.factories import base_fingerprint_kwargs

        def build(run_id: str) -> dict:
            kwargs = base_fingerprint_kwargs()
            kwargs.update(run_id=run_id)
            kwargs.pop("created_at")
            return build_config_fingerprint(**kwargs)

        # Descending run IDs would win a run_id tie-break. Creation order must win.
        first, second, third = build("run-z"), build("run-m"), build("run-a")
        self.assertLess(first["created_at"], second["created_at"])
        self.assertLess(second["created_at"], third["created_at"])
        result = select_baseline(make_fingerprint(run_id="run-c"), [first, second, third])
        self.assertEqual(result["baseline_run_id"], "run-a")
