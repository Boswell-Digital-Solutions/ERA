# ERA Known Issues

Findings for this repo. Each entry has a date, the problem, the root cause, the fix if any, and an explicit scope (open or closed).

## 2026-09-30 — Legacy efficiency baseline ties within one second

**Status: OPEN.**

**Problem.** `build_efficiency_baseline_artifact` in `era_core/efficiency.py` picks the latest prior efficiency run. Two runs that finish in the same second tie. The `run_id` suffix is random, so the sort does not follow creation order. The tool can select an older run as the baseline.

**Root cause.** The sort key is `completed_at`. `utc_now_text` has one-second resolution. The run ID (`YYYYMMDDTHHMMSSZ-<random>`) does not break ties in time order.

**Scope.** This affects `EfficiencyWorkloadManifest.v1` workloads and any v2 workload without an `evaluation` block. Workloads with an `evaluation` block are not affected. Their fingerprints carry a microsecond `created_at` (fixed in BDS-ERA-EVAL-v0.1 WP06).

**Fix (not applied).** Order by a microsecond timestamp or a monotonic sequence written into `run.json`. Keep the change out of the v1 baseline artifact shape. Add a test with two runs in one second.

**Found by.** BDS-ERA-EVAL-v0.1 WP06 proving run. No plan covers this path.

## 2026-09-30 — Deleting an old run invalidates newer runs that used it as a baseline

**Status: OPEN, by design.**

**Problem.** `validate_run_dir` checks that the recorded baseline run still exists and still validates (BDS-ERA-EVAL-v0.1 WP05). A newer run fails validation if its baseline run folder is deleted.

**Root cause.** The check makes a stale baseline reference fail closed.

**Scope.** Only runs whose workload has an `evaluation` block. Archive old run folders together with the runs that depend on them. A future work package can add a baseline snapshot inside the newer run, so the newer run does not depend on the older folder.
