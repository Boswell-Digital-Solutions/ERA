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

**Status: CLOSED 2026-10-17 for the consumer surfaces (producer side closed 2026-09-30). The signature limit below stays.**

**Problem.** ERA writes `evaluation_export.json`. Nothing reads it. DataForge Local has no ERA or evaluation ingestion surface. Forge_Command shows ERA evidence only through the Centipede inbox, which takes findings and incidents, not evaluation claims.

**Progress.** The contract is admitted in `forge_contract_core` (`era_evaluation_export` v1, RFC-ERA-EVAL-01, accepted 2026-09-30). ERA emits the admitted artifact and validates it against the contract's own vectors and validator.

**Open (as of 2026-09-30, now stale).** DataForge Local drop-directory intake, and a separate Forge_Command read-only route. Each is its own bounded plan and PR. The envelope `signature` is an unsigned digest reference: ERA holds no signing key. A consumer must not read it as a signature.

**Correction 2026-10-17.** The "Open" paragraph above is stale. Both consumer surfaces exist on the remote default branches. The BugCheck capability reconciliation (`BDS-ECOSYSTEM-BUGCHECK-CAPABILITY-RECON-v0.1`, capability C12; Forge_Command PR #638) found the Forge_Command route. This correction re-verified the full chain:

- ERA publishes the export to the DataForge Local inbox (`era_integrations/inbox_publish.py:1-20`, ERA-PUB-01).
- DataForge Local stores it from the drop directory (`proving_slice/services/era_drop_intake.py:1-23` on `dataforge-Local` `origin/master` at `e7ea1c1`, DFL-ERA-01). It serves two read-only routes (`app/api/era_evaluation_router.py:31`, mounted at `app/main.py:95`, DFL-ERA-02).
- Forge_Command forwards those reads and has no write route (`src-tauri/src/api/routes/era_evaluation.rs:1-6`, registered at `src-tauri/src/fc_rest_server.rs:116-121`, on `origin/main` at `cc2391bf`, FC-ERA-01, PR #399).

**Still open, outside this entry.** The signature limit above stays: a consumer must not read the digest reference as a signature. An ERA run carries its own `run_id`. It has no binding to a Forge_Command run or RunIntent. That binding is BugCheck design work that Forge_Command owns. It is not an ERA defect. No runtime test of the chain was run for this correction; the evidence is source reading only.


## 2026-09-30 — KI-ERA-20260930-001: Documentation builder ignores --check and rewrites the compiled reference

**Status: OPEN — confirmed by source inspection; repair not applied.**

**Source lock.** `Boswell-Digital-Solutions/ERA@2d8b1746583bb1db4fe7c1bf400613e51d2ec700` (`master`, rechecked 2026-09-30).

**Evidence.** Complete reads of `doc/system/BUILD.sh` and `doc/system/validate_snapshots.sh`. The builder does not parse positional arguments. After temporary assembly and marker validation, it unconditionally executes `cp "$TMP_OUTPUT" "$ROOT_DIR/$OUTPUT"` and `chmod 664 "$ROOT_DIR/$OUTPUT"`, then reports `BUILD_OK`. The validator checks required documentation markers, not equality with the committed reference.

**Problem and impact.** `bash doc/system/BUILD.sh --check` follows the normal write path instead of a non-mutating parity check. With valid source structure and markers, a stale `doc/ERASYSTEM.md` can be overwritten rather than rejected. A successful invocation is therefore not evidence that the committed reference was already current. This is a missing verification mode; the inspected ERA chapters document assembly and do not make QRE's explicit `BUILD_STALE` promise.

**Root cause.** Argument dispatch and a comparison against the existing output are absent. Structural marker validation is being performed, but it is not documentation parity validation.

**Verification limits.** No script or test suite was executed for this finding. Current compiled-document staleness, the existence of an active CI caller passing `--check`, and the state of any runtime deployment were not established. This entry records observable script behavior, not a demonstrated CI failure or stale artifact.

**Bounded repair proposal — not authorization.** Add explicit build/check argument handling. Preserve intentional normal assembly. In check mode, assemble and validate in temporary storage, compare against the existing committed output without creating or modifying repository files, return nonzero for stale or missing output, and reject unsupported arguments before side effects. Do not hand-edit the compiled reference or alter ERA runtime/evaluation behavior.

**Closure evidence required.** Regression tests must prove: a current reference passes without byte or mode changes; stale and missing references fail without repair or creation; invalid source/validation failures leave the output unchanged; unsupported arguments fail without writes; and explicit normal build still regenerates the reference. Run these in an isolated test checkout and record the exact repair head and results, including repository state before and after check mode.

**Related findings.** `failureforge: KI-FFG-20260930-001`; `bds-QRE: KI-QRE-20260930-001`. Each repository needs its own repair and evidence. Fixing one does not close the others.

**Review qualification.** `doc/system/06-verification.md` describes GATE-06 as seven local-sleep scenarios with no model, provider, agent, or network calls. That proving run establishes bounded claim-processing/reconstruction behavior, not live-model or live-agent evaluation coverage. This is a verification limit, not an additional confirmed implementation defect; no live campaign is authorized by this entry.

**Authority and scope.** Operator requested known-issues documentation on 2026-09-30. This entry changes no script, generated reference, runtime, contract, baseline, CI enforcement, or existing issue disposition. Repair and closure remain separate work.
