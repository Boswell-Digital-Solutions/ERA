# BDS-ERA-EVAL-v0.1 — GATE-00 Source Lock (CP0 / WP00)

Date: 2026-09-30
Plan: BDS-ERA-EVAL-v0.1, lifecycle `proposed`. Drive: `/Forge/Plans/BDS-ERA-EVAL-v0.1`.
Authorization: operator approved D1 and D2 in session. This packet is read-only evidence. No code changed.

## Result

**GATE-00: PASS.** Two plan assumptions need correction (see Findings). Neither one blocks CP1.

## Immutable anchor

| Item | Value |
|---|---|
| Repo | `Boswell-Digital-Solutions/ERA` |
| Head (`origin/master`) | `13180a8837590476e3c8ff6f115f8a3c571b768d` |
| Plan anchor head | same value. No drift. |
| Test baseline | `python3 -m pytest`: 40 passed |
| Doc parity | `bash doc/system/BUILD.sh` leaves the tree clean. Parity holds. |

Blob hashes at the head:

| File | Blob |
|---|---|
| `repo.manifest.yaml` | `b88b831569c0ffe293f84f79ed3f671915509ce9` |
| `README.md` | `6a390f3f38a06f8813c61be235c958e196ed55fd` |
| `era_core/efficiency.py` | `51d10b0fba5db4b03a3da40ead2859cdb2501ddf` |
| `era_core/contracts.py` | `20eeeb2ce7085c835c1e5707d041280d435b1ee6` |
| `era_core/review_writer.py` | `33a6ba59216678fa5668bbe4b1a189e00a4051d7` |
| `era_core/validation.py` | `1856a1dcf5fac2f14220f7f3d7891fd00b833bf6` |
| `era_cli/commands/run.py` | `199e84ac2fce1f0b6fcf35ef895623ed6fc09903` |
| `tests/test_efficiency.py` | `366075059b3e66607b3590e956424da5291f3576` |

## Collision and supersession checks

- No file in the repo defines `EvaluationConfigFingerprint`, `QualityGate`, `MetricVector`, or `QualityEfficiencyComparison`. No name collision.
- No newer ERA plan exists in `docs/ERA_Plan_Set_MD/` (12 files, ERA-01A to ERA-03 roadmap).
- A Drive search for ERA plans after 2026-09-01 found only this plan set. Nothing supersedes it.
- The ERA manifest still declares the roles that the plan assumes (see `CLAUDE.md` Owns / Does Not Own).
- The `--trusted-target` gate and the read-only posture are unchanged. README states "no execution sandbox yet".

## Current call graph (efficiency lane)

`era_cli/commands/run.py`:

1. `load_efficiency_workload_manifest` → manifest dict (`schema_version` defaults to `EfficiencyWorkloadManifest.v1`).
2. `detect_efficiency_commands` → `PlannedCommand` list. It applies the executable allowlist and the cwd-escape check. Workload thresholds go into `lane_metadata`.
3. Commands run. The timing summary and variance class go into `lane_metadata`.
4. `build_efficiency_baseline_artifact` → `EfficiencyBaselineArtifact.v1`.
5. `build_efficiency_normalized_results` → `ToolNormalizedResult.v1`. Only a `regression` makes a finding.
6. `determine_efficiency_classification` (`review_writer.py:42`) → lane class.
7. Evidence written to `evidence/efficiency/{workload_manifest,baseline_artifact,efficiency_evidence_bundle}.json`. `validation.py:414-430` checks them.

## Current behavior that WP02 to WP05 change

**Baseline selection** (`efficiency.py:273-294`). Filters are `repo_id` and lane, then `commit_sha` (if a baseline commit is given) or `branch`. It takes the latest by `completed_at`. It reads no workload identity, command digest, hardware, or config. This is the gap the plan targets.

**Comparison** (`efficiency.py:301-332`). Status order: failed or unproven, no baseline, unstable, then percent delta against thresholds. Only median wall time is compared.

**Lane classification vocabulary today:** `blocked_by_missing_tool`, `blocked_by_missing_evidence`, `unproven`, `regression_with_baseline`, `unstable`, `within_expected_range`.

**Validation.** `validation.py` checks only that `schema_version` exists and that `baseline.run_id` matches `run.json`. It does not check the baseline artifact hash.

## Findings

1. **Path correction.** The plan lists `run.py`. The real path is `era_cli/commands/run.py`. Use this path in the CP1 allowlist.
2. **No lane-level `improvement`.** An `improvement` comparison exists only inside `EfficiencyBaselineArtifact`. It creates no finding. The lane class collapses to `within_expected_range` (`review_writer.py:57-62`). WP04 must add `quality_blocked`, `quality_unproven`, `incomparable`, and `improvement` (or a compatible equivalent) to the lane vocabulary. Plan section 06 already allows this "smallest compatible surface".
3. **`no_baseline` is a comparison status here.** The plan's decision table uses the same word. WP04 must keep the legacy value for v1 workloads.
4. **Baseline hash is not verified.** `EfficiencyBaselineArtifact.v1` carries `sha256`. `_validate_embedded_hash` (`validation.py:53`) covers bundles, normalized results, findings, drafts, and scores, but not this file. WP05 must add this check for the new artifacts. Decide separately whether to add it for the legacy artifact.
5. **Drive hygiene.** A 1 KB empty copy of `..__04_CONTRACTS_AND_PROVENANCE_MODEL.md` sits in the Drive root, not in the plan folder. The plan folder holds the full copy. Nothing depends on the stray file. The operator can delete it.
6. **No `docs/KNOWN_ISSUES.md` in ERA.** Create it when the first finding needs a durable record. Findings 2 and 4 are design inputs to CP1, not defects, so this packet does not create it.

## Proposed CP1 allowlist (WP01 + WP02)

Allowed to add or edit:

- `era_core/eval_contracts.py` (new): four dataclass/dict contracts, validators, canonical hashing
- `era_core/eval_comparability.py` (new): dimension normalization and baseline match policy
- `era_core/hashing.py`: only if a canonical-JSON helper is missing (`sha256_json` exists; verify first)
- `tests/test_eval_contracts.py`, `tests/test_eval_comparability.py` (new)
- `tests/fixtures/eval/**` (new): positive and malformed fixtures
- `doc/system/02-contract-surface.md` and a rebuild of `doc/ERASYSTEM.md`, if docs are in scope

Not allowed in CP1:

- Edits to `efficiency.py`, `review_writer.py`, `validation.py`, or `run.py`. Wiring belongs to WP03 to WP05.
- Any change to `forge_contract_core`, `Forge_Command`, or `DataForge`.
- Live model, provider, or agent calls. No sandbox work.
- Edits to the generated agent files (`AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `GEMINI.md`).

Verification for CP1: `python3 -m pytest` (40 existing tests must stay green) and `bash doc/system/BUILD.sh`.
Stop conditions: any need to edit a file outside the allowlist; any contradiction of a Binding Ruling.

## Next authorization needed

Approve CP1 (WP01 to WP02) with the allowlist above. Confirm whether docs are in scope.

## Addendum 1 — head moved (2026-09-30)

PR #5 (Slice 03, contained execution sandbox) merged after the first lock. GATE-00 is re-checked against the new head.

| Item | Value |
|---|---|
| New head (`origin/master`) | `7eac6716058d327055774cd65e2d8530d0b4883c` |
| Files changed since `13180a8` | `README.md`, `era_cli/commands/run.py`, `era_core/command_runner.py`, new `era_core/sandbox.py`, new `tests/test_sandbox.py` |
| Test baseline | 43 tests on master (87 with WP01 and WP02) |
| Doc parity | `BUILD.sh` leaves the tree clean |

New blobs: `README.md` `b69b7db0f32555abd74a0ca594e10299a5152021`, `era_cli/commands/run.py` `d16f63fc6b09cc192ca40cc0db188b99e55d5702`, `era_core/command_runner.py` `dc34a51c3834a36afb796202934085a30691f179`.

**Result: GATE-00 still passes.** The change does not touch the efficiency lane, the baseline logic, or any WP01 and WP02 file. The rebase was clean. Three plan statements are now out of date:

1. **AUTHORITY_GAP-02 is partly closed.** ERA now has a contained backend: no network, and the target repo behind an overlay. Section 02 says "ERA currently has no sandbox". Section 02 also says ERA "does not own the sandbox". The sandbox lives inside ERA. The operator must rule whether `era_core/sandbox.py` counts as the "authorized isolation provider" for D5. Until then, treat agentic and untrusted workloads as still held (WP11).
2. **The trust gate changed.** `--trusted-target` is now needed only when containment is unavailable or off. Plan case N19 ("untrusted target without attestation refuses") must read: refuses when there is neither containment nor attestation. Ruling 9 and the non-goal "do not weaken --trusted-target" still hold, because the gate fails closed in both paths.
3. **Disclosed limit.** A contained run can still read other host paths. It is not a full jail.

Effect on CP1: none. CP2 must read `execution_posture` (`sandbox`, `network`, `target_filesystem`) when it binds fingerprints, because a contained run has no network. A non-hermetic workload fails in a contained run by design. Record the posture in the execution identity at WP03.
