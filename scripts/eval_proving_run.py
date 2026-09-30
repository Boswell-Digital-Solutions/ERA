#!/usr/bin/env python3
"""BDS-ERA-EVAL-v0.1 WP06: deterministic proving run (GATE-06).

Builds a throwaway trusted fixture repository and runs seven scenarios through
the real ERA run path. Each scenario must reach its expected claim, validate, and
be rebuilt from the artifacts on disk with the same result. The run uses local
sleep commands only. It calls no model, provider, agent, or network.

Usage: python3 scripts/eval_proving_run.py [--out receipt.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from era_cli.commands.run import execute_run  # noqa: E402
from era_core.artifact_paths import utc_now_text  # noqa: E402
from era_core.eval_reconstruct import compare_to_stored  # noqa: E402
from era_core.hashing import sha256_json, write_json  # noqa: E402
from era_core.validation import validate_run_dir  # noqa: E402

PLAN_ID = "BDS-ERA-EVAL-v0.1"
WORKLOAD_ID = "proving_probe"
EVAL = "evidence/efficiency/eval/proving_probe"

EVALUATION = {
    "subject_kind": "repository_command",
    "runtime_identity": {"interpreter": "python3"},
    "evaluation_identity": {
        "suite_id": "proving-suite",
        "suite_version": "1",
        "dataset_or_fixture_hash": "proving-data-1",
        "scorer_id": "proving-scorer",
        "scorer_version": "1",
        "harness_id": "era-proving",
        "harness_version": "1",
        "split_or_holdout_class": "public_fixture",
        "quality_floor_policy_id": "proving-floor-1",
    },
    "execution_identity": {"hardware_fingerprint": "proving-host", "concurrency": 1, "batch_size": 1},
    "quality_gate_policy": {
        "quality_floors": {"accuracy": {"min": 0.9}},
        "quality_results_path": "quality/results.json",
    },
    "metrics": {"median_ms": "lower_is_better"},
}


def sleep_command(seconds: float) -> list[str]:
    return ["python3", "-c", f"import time; time.sleep({seconds})"]


def unstable_command(counter: Path) -> list[str]:
    """Three iterations of about 20, 400, and 20 ms. The variance class is always unstable."""
    code = (
        "import sys,time,pathlib;p=pathlib.Path(sys.argv[1]);"
        "n=int(p.read_text()) if p.exists() else 0;p.write_text(str(n+1));"
        "time.sleep([0.02,0.4,0.02][n%3])"
    )
    return ["python3", "-c", code, str(counter)]


def scenarios(counter: Path) -> list[dict[str, Any]]:
    other_data = json.loads(json.dumps(EVALUATION))
    other_data["evaluation_identity"]["dataset_or_fixture_hash"] = "proving-data-2"
    return [
        {"name": "baseline", "command": sleep_command(0.4), "accuracy": 0.95,
         "expect": {"claim": "no_baseline", "efficiency": "not_evaluated", "lane": "unproven", "findings": 0}},
        {"name": "allowed_improvement", "command": sleep_command(0.05), "accuracy": 0.95,
         "expect": {"claim": "permitted", "efficiency": "improvement", "lane": "within_expected_range", "findings": 0}},
        {"name": "allowed_regression", "command": sleep_command(0.6), "accuracy": 0.95,
         "expect": {"claim": "permitted", "efficiency": "regression", "lane": "regression_with_baseline", "findings": 1}},
        {"name": "quality_blocked_faster_candidate", "command": sleep_command(0.02), "accuracy": 0.40,
         "expect": {"claim": "quality_blocked", "efficiency": "not_evaluated", "lane": "quality_blocked", "findings": 0}},
        {"name": "quality_unproven_candidate", "command": sleep_command(0.02), "accuracy": None,
         "expect": {"claim": "quality_unproven", "efficiency": "not_evaluated", "lane": "quality_unproven", "findings": 0}},
        {"name": "incomparable_config", "command": sleep_command(0.05), "accuracy": 0.95, "evaluation": other_data,
         "expect": {"claim": "incomparable", "efficiency": "not_evaluated", "lane": "incomparable", "findings": 0}},
        {"name": "unstable_measurement", "command": unstable_command(counter), "accuracy": 0.95,
         "expect": {"claim": "no_claim_unstable", "efficiency": "unstable", "lane": "unstable", "findings": 0}},
    ]


def write_manifest(era_root: Path, repo_name: str, command: list[str], evaluation: dict[str, Any]) -> None:
    directory = era_root / "config" / "workload_manifests"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{repo_name.lower()}.json").write_text(
        json.dumps(
            {
                "schema_version": "EfficiencyWorkloadManifest.v2",
                "repo_id": repo_name,
                "workloads": [
                    {
                        "workload_id": WORKLOAD_ID,
                        "label": "proving probe",
                        "category": "runtime_benchmark",
                        "command": command,
                        "cwd_subpath": ".",
                        "runner": "internal_timer",
                        "iterations": 3,
                        "regression_threshold_pct": 25.0,
                        "improvement_threshold_pct": 25.0,
                        "evaluation": evaluation,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def init_repo(path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    git("init")
    git("branch", "-m", "main")
    (path / "README.md").write_text("proving fixture\n", encoding="utf-8")
    git("add", "README.md")
    git("-c", "user.name=ERA", "-c", "user.email=era@example.com", "commit", "-m", "init")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_proving(workdir: Path) -> dict[str, Any]:
    era_root, repo = workdir / "era", workdir / "repo"
    era_root.mkdir()
    repo.mkdir()
    init_repo(repo)
    artifacts_root = era_root / "artifacts" / "era-runs"
    results: list[dict[str, Any]] = []

    for scenario in scenarios(workdir / "unstable.counter"):
        quality_file = repo / "quality" / "results.json"
        quality_file.parent.mkdir(exist_ok=True)
        if scenario["accuracy"] is None:
            quality_file.unlink(missing_ok=True)
        else:
            quality_file.write_text(
                json.dumps({"metric_results": {"accuracy": scenario["accuracy"]}, "sample_count": 20}), encoding="utf-8"
            )
        write_manifest(era_root, repo.name, scenario["command"], scenario.get("evaluation", EVALUATION))
        run_dir = execute_run(repo_path=repo, lanes=["efficiency"], mode="full", artifacts_root=artifacts_root)

        comparison = _load(run_dir / EVAL / "comparison.json")
        run_json = _load(run_dir / "run.json")
        findings = _load(run_dir / "findings.json")
        hashes = _load(run_dir / "hashes.json")
        score = next(s for s in findings["era_scores"] if s["scope"] == "lane" and s["lane"] == "efficiency")
        finding_count = len([f for f in findings["era_findings"] if f["lane"] == "efficiency"])
        validation = validate_run_dir(run_dir)
        rebuilt = compare_to_stored(run_dir, WORKLOAD_ID)
        chain_hashes = {
            item["kind"]: item["sha256"] for item in hashes["evidence_hash_chain"].get("evaluation_artifacts", [])
        }
        actual = {
            "claim": comparison["claim_status"],
            "efficiency": comparison["efficiency_status"],
            "lane": score["classification"],
            "findings": finding_count,
        }
        checks = {
            "outcome_matches_expected": actual == scenario["expect"],
            "run_validates": validation["ok"],
            "comparison_in_hash_chain": chain_hashes.get("comparison") == comparison["sha256"],
            "reconstruction_matches_stored": rebuilt["match"],
        }
        results.append(
            {
                "scenario": scenario["name"],
                "run_id": run_dir.name,
                "expected": scenario["expect"],
                "actual": actual,
                "quality_status": comparison["quality_status"],
                "comparability_status": comparison["comparability_status"],
                "baseline_run_id": comparison["baseline_run_id"],
                "blocked_reasons": comparison["blocked_reasons"],
                "baseline_rejections": comparison["baseline_rejections"],
                "comparison_sha256": comparison["sha256"],
                "execution_posture": {
                    key: run_json["execution_posture"].get(key)
                    for key in ("sandbox", "network", "target_filesystem", "target_trust")
                },
                "validation_errors": validation["errors"],
                "reconstruction_differences": rebuilt["differences"],
                "checks": checks,
                "passed": all(checks.values()),
            }
        )

    receipt = {
        "schema_version": "ERAEvalProvingReceipt.v1",
        "plan_id": PLAN_ID,
        "gate": "GATE-06",
        "workload_id": WORKLOAD_ID,
        "live_dependencies": {"model_calls": 0, "provider_calls": 0, "agent_runs": 0, "network": "not used"},
        "scenarios": results,
        "gate_06_pass": all(item["passed"] for item in results),
        "created_at": utc_now_text(),
    }
    receipt["sha256"] = sha256_json(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="Write the receipt JSON here.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="era-proving-") as temp:
        receipt = run_proving(Path(temp))
    if args.out:
        write_json(args.out, receipt)
    for item in receipt["scenarios"]:
        print(f"{'PASS' if item['passed'] else 'FAIL'}  {item['scenario']:<34} claim={item['actual']['claim']}")
    print(f"GATE-06: {'PASS' if receipt['gate_06_pass'] else 'FAIL'}")
    return 0 if receipt["gate_06_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
