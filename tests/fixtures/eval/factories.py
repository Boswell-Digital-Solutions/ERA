from __future__ import annotations

import copy
from typing import Any

from era_core.eval_contracts import build_config_fingerprint

FIXED_TIME = "2026-09-30T00:00:00Z"


def base_fingerprint_kwargs() -> dict[str, Any]:
    return {
        "run_id": "run-a",
        "repo_id": "fixture_repo",
        "workload_id": "fixture_workload",
        "subject_kind": "local_model",
        "source_commit_sha": "a" * 40,
        "subject_identity": {"model_id": "fixture-model", "model_revision": "rev1", "quantization": "q8"},
        "runtime_identity": {"engine": "fixture-engine", "engine_version": "1.0", "prompt_template_hash": "p1"},
        "evaluation_identity": {
            "suite_id": "suite",
            "suite_version": "1",
            "dataset_or_fixture_hash": "d1",
            "scorer_id": "scorer",
            "scorer_version": "1",
            "harness_id": "harness",
            "harness_version": "1",
            "split_or_holdout_class": "public_fixture",
            "quality_floor_policy_id": "floor-1",
        },
        "execution_identity": {"hardware_fingerprint": "hw1", "concurrency": 1, "batch_size": 1},
        "created_at": FIXED_TIME,
    }


def make_fingerprint(**overrides: Any) -> dict[str, Any]:
    """Build a fingerprint. Dotted keys such as ``evaluation_identity.suite_version`` patch nested fields."""
    kwargs = copy.deepcopy(base_fingerprint_kwargs())
    for key, value in overrides.items():
        if "." in key:
            group, field = key.split(".", 1)
            kwargs[group][field] = value
        else:
            kwargs[key] = value
    return build_config_fingerprint(**kwargs)
