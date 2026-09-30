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

**Status: CLOSED 2026-09-30** (operator decision 4: persistence keeps the baseline chain).

**Problem.** `validate_run_dir` needed the baseline run folder (BDS-ERA-EVAL-v0.1 WP05). A newer run failed validation if that folder was deleted.

**Fix.** Each comparison that names a baseline now stores a sealed `BaselineSnapshot.v1` in the newer run. It copies the baseline's fingerprint, quality gate, and metric vector. Validation checks the claim against the snapshot. If the baseline folder still exists, it must match the snapshot. A run can be archived without breaking newer runs. The evaluation export carries a `baseline` block from the snapshot.

**Limit.** Reconstruction from the snapshot proves the claim given the recorded baseline. It cannot re-check which other prior runs were rejected. Runs made before this change have no snapshot and still need the baseline folder.

## 2026-09-30 — No downstream consumer for evaluation evidence

**Status: OPEN.**

**Problem.** ERA writes `evaluation_export.json` (`ERAEvaluationExport.v1`) for runs with opted-in workloads. Nothing reads it. DataForge Local has no ERA or evaluation ingestion surface. Forge_Command shows ERA evidence only through the Centipede inbox, which takes findings and incidents, not evaluation claims.

**Root cause.** The export contract is local to ERA (BDS-ERA-EVAL-v0.1 AUTHORITY_GAP-01). A consumer in another repo needs a promoted contract in `forge_contract_core`. Promotion is a separate authorization.

**Scope.** ERA side is closed (export, validation, hash chain). Persistence, the review surface, and contract promotion are open and need operator decisions. See `docs/eval/BDS-ERA-EVAL-v0.1_WP12_INTERFACE.md`.
