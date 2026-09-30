# BDS-ERA-EVAL-v0.1 — GATE-06 Proving Run (CP4 / WP06)

Date: 2026-09-30
Authorization: operator authorized WP06 on 2026-09-30. HELD work (WP07 to WP12) stays out of scope.

## Result

**GATE-06: PASS.** Seven scenarios reach their expected claim. Each run validates. Each claim is rebuilt from the artifacts on disk with the same result.

Receipt: [BDS-ERA-EVAL-v0.1_GATE-06_proving_receipt.json](BDS-ERA-EVAL-v0.1_GATE-06_proving_receipt.json).

## How to run it

```bash
python3 scripts/eval_proving_run.py --out receipt.json
```

The script makes a throwaway trusted git repository. It runs ERA through the real run path. It uses local `sleep` commands only. It calls no model, provider, agent, or network. The receipt states this in `live_dependencies`.

## Scenarios

All scenarios use one workload and one artifact root, in this order. Each scenario sees only the runs before it.

| # | Scenario | Setup | Expected claim | Lane class | Findings |
|---|---|---|---|---|---:|
| 1 | baseline | quality pass, 0.4 s | `no_baseline` | `unproven` | 0 |
| 2 | allowed_improvement | quality pass, 0.05 s | `permitted` (improvement) | `within_expected_range` | 0 |
| 3 | allowed_regression | quality pass, 0.6 s | `permitted` (regression) | `regression_with_baseline` | 1 |
| 4 | quality_blocked_faster_candidate | quality 0.40 (floor 0.90), 0.02 s | `quality_blocked` | `quality_blocked` | 0 |
| 5 | quality_unproven_candidate | no quality results file | `quality_unproven` | `quality_unproven` | 0 |
| 6 | incomparable_config | dataset hash changed | `incomparable` | `incomparable` | 0 |
| 7 | unstable_measurement | timings near 20, 400, 20 ms | `no_claim_unstable` | `unstable` | 0 |

Only the permitted regression makes a finding. Scenario 4 is faster than every baseline and still gets no improvement claim.

## Checks for each scenario

1. The actual claim, efficiency status, lane class, and finding count equal the expected values.
2. `validate_run_dir` passes.
3. The comparison hash in `hashes.json` equals the comparison file.
4. `era_core/eval_reconstruct.py` rebuilds the decision from the run folder alone. It counts only runs created before the candidate. The rebuilt decision must equal the stored one.

Tests in `tests/test_eval_proving_run.py` also prove that a changed stored claim and a changed quality gate make the rebuild differ.

## Fixes found while building the run

**Same-second baseline ties.** Baseline selection ordered prior runs by `created_at` with one-second resolution. The random run-ID suffix broke ties, so two runs in one second could pick either as the latest. New fingerprints now carry a microsecond `created_at`. A test covers descending run IDs.

The legacy v1 baseline (`efficiency.py`) still orders by `completed_at` at one-second resolution. That path is out of scope for this plan. It has the same tie risk. Recorded in the amendment.

## Limits

- The proof runs on a trusted target with no sandbox (`sandbox: none`). It shows the claim semantics only. It does not show contained execution.
- Timing uses real sleeps. The margins are wide (0.4 s against 0.05 s), and the receipt was stable in 5 repeat runs. A very loaded host could still add jitter.
- The receipt is evidence of a run. It is not canonical truth until reconciled downstream.

## Authorization boundary

GATE-06 closes ERA-EVAL-01. It does not authorize telemetry adapters, model calls, judge use, agent execution, DataForge writes, UI work, or contract promotion (WP07 to WP12).
