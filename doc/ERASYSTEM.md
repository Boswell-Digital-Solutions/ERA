        # ERA - Compiled System Reference

        **Designation:** ERA
        **Document role:** Canonical compiled technical reference for Evidence Review and Assurance
        **Source:** `doc/system/`
        **Build command:** `bash doc/system/BUILD.sh`
        **Document version:** 2.0 (2026-06-22) - canonical compliance migration
        **Protocol:** BDS Documentation Protocol v2.0; BDS Repo Documentation System Canonical Compliance Standard

        > **Generated artifact warning:** `doc/ERASYSTEM.md` is assembled output. Edit
        > the source modules under `doc/system/` and rebuild. Hand edits to the
        > compiled artifact are overwritten by the next build.

        Assembly contract:

        - Command: `bash doc/system/BUILD.sh`
        - Validation: `bash doc/system/validate_snapshots.sh` runs during assembly
        - Primary output: `doc/ERASYSTEM.md`

        This `doc/system/` tree is the canonical source of truth for ERA. It uses
        explicit **truth classes**: canonical facts define repo role, authority
        boundaries, contract behavior, runtime behavior, and verification doctrine;
        snapshot facts are dated, audit-derived counts and current implementation
        inventory that may drift between audits.

        | Part | File | Contents |
        | --- | --- | --- |
        | §1 | `01-overview.md` | 01 Overview |
| §2 | `02-contract-surface.md` | 02 Contract Surface |
| §3 | `03-runtime-boundary.md` | 03 Runtime Boundary |
| §4 | `04-dependencies.md` | 04 Dependencies |
| §5 | `05-governance.md` | 05 Governance |
| §6 | `06-verification.md` | 06 Verification |
| §7 | `90-appendices.md` | 90 Appendices |

        ## Quick Assembly

        ```bash
        bash doc/system/BUILD.sh
        ```

---

            # Overview

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            ERA means Evidence Review and Assurance. It is a bounded internal-control subsystem for the Forge ecosystem.

The current doctrine is: ERA finds, measures, proves, and reports. ERA does not fix.

---

            # Contract Surface

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            ERA emits structured artifacts for lane findings, scores, evidence hash chains, review artifacts, differential selection, Centipede export, and Self-Healing projection proofs.

Contract truth lives in `era_core/contracts.py`, the CLI outputs under `artifacts/era-runs/<run_id>/`, and the plan set under `docs/ERA_Plan_Set_MD/`.

## Evaluation Contracts (BDS-ERA-EVAL-v0.1, local)

ERA defines four local evaluation contracts in `era_core/eval_contracts.py`. They are `EvaluationConfigFingerprint.v1`, `QualityGateArtifact.v1`, `MetricVector.v1`, and `QualityEfficiencyComparison.v1`. They are not in `forge_contract_core`. Promotion needs a separate authorization.

Each contract carries a `sha256` over its canonical JSON without the `sha256` key. Each validator returns a list of errors. An empty list means the artifact is valid.

The fingerprint carries a `config_digest`. The digest covers the subject, runtime, evaluation, and execution identity. It does not cover the run ID, the time, or the commit SHA. Two runs of one configuration have the same digest.

A quality floor is `min`, `max`, or `equals`. A missing result or a zero sample count gives `unproven`. It never gives `passed`.

A `QualityEfficiencyComparison.v1` cannot name `improvement` or `regression` unless the quality gate passed, the baseline is comparable, and the claim is `permitted`.

`era_core/eval_comparability.py` compares two fingerprints on the required dimensions. A different value gives `incomparable`. A missing or unrecognized dimension gives `unknown`. Only a manifest can waive a dimension. `select_baseline` picks the latest comparable prior run and lists the rejected runs with reasons.

## Quality Gate in the Efficiency Lane (WP03)

A workload opts in with an `evaluation` block (`EfficiencyWorkloadManifest.v2`). A workload without the block keeps the v1 behavior. `era_core/eval_lane.py` builds a fingerprint, a quality gate, and a metric vector for each opted-in workload. It writes them under `evidence/efficiency/eval/<workload>/`.

ERA reads quality results from a file that already exists in the target tree. A contained run discards writes to the target, so the workload command cannot create that file. A missing file gives `quality_unproven`. A misdeclared block gives `evidence_blocked`.

The execution identity includes the sandbox posture (`sandbox`, `sandbox_backend`, `network`, `target_filesystem`). A contained run and an uncontained run never compare as equal.

When the quality gate is not `passed`, the workload status becomes `quality_blocked`, `quality_unproven`, or `evidence_blocked`. The timing status stays visible as `timing_comparison_status`. A quality failure is never reported as a regression. The lane classification follows the same order.

## Claim Gate (WP04)

`era_core/eval_claims.py` selects the baseline and decides the claim. A prior run is a baseline only when its evidence validates, its fingerprint matches the required dimensions, and its quality gate passed. ERA keeps every rejected run in `baseline_rejections` with a reason: `evidence_invalid`, `fingerprint_incomparable`, `quality_failed`, or `quality_unproven`. The result is written as `comparison.json` in the workload folder.

The checks run in this order, and the first one that fails sets the claim:

1. Broken or missing evidence gives `evidence_blocked`.
2. A failed quality gate gives `quality_blocked`.
3. Unproven quality gives `quality_unproven`.
4. No prior run gives `no_baseline`.
5. Prior runs exist but none qualifies. Comparable priors that failed or lacked quality give `no_baseline`. Otherwise priors that do not match give `incomparable`. Priors with unusable evidence give `evidence_blocked`.
6. Unstable timing gives `no_claim_unstable`.
7. Otherwise the median delta against the workload thresholds gives `improvement`, `regression`, or `within_range`, with the claim `permitted`.

`no_claim_unstable` and `no_baseline` were added to the plan's claim statuses. The operator ruled on `no_claim_unstable` on 2026-09-30. The plan's decision table already lists `no_baseline`.

The workload status in `baseline_artifact.json` follows the claim. A `regression` that is `permitted` still makes the existing efficiency finding. All other blocked claims are evidence only and make no finding.

## Evidence Chain and Review (WP05)

`hashes.json` lists every evaluation artifact in `evidence_hash_chain.evaluation_artifacts`. Each entry has the workload, the kind, the run-relative path, and the embedded hash.

`era_core/eval_validation.py` runs inside `validate_run_dir`. It fails closed in each of these cases:

- An artifact is missing, or a chain entry names an artifact that does not exist.
- A hash differs from the bundle reference or the chain entry.
- An artifact does not validate, or belongs to another run or workload.
- The quality gate or the metric vector references another fingerprint.
- The comparison disagrees with its fingerprint, its quality gate, or `baseline_artifact.json`.
- The recorded baseline run is missing, no longer validates, did not pass quality, or is no longer comparable.

An attacker can refresh the file entries in `hashes.json`. The reference and linkage checks still catch an edited artifact.

`review.md` has a "Quality-Gated Evaluation" section for each opted-in workload. It shows the claim status, the quality status and reasons, the candidate fingerprint, the baseline run and fingerprint, the comparability and blocked reasons, the stability, each metric delta on its own row, the rejected baselines, and the artifact hashes. The word `improvement` appears only for a permitted claim.

## Inference Telemetry (WP07)

ERA does not measure an inference engine. An external tool writes an `InferenceTelemetry.v1` file into the target tree. A workload names it in `evaluation.telemetry_policy.telemetry_results_path`. `era_core/eval_telemetry.py` reads it and adds each declared metric to the `MetricVector.v1`.

Supported metrics: `ttft_ms`, `tpot_ms`, `itl_ms`, `output_tokens_per_second`, `throughput_rps`, `ram_mb`, `vram_mb`, `context_tokens`, `output_tokens`. Only metrics with a direction in `evaluation.metrics` are used. A metric with bad samples is left out and named in the review.

Each metric value is the median. A metric listed in `percentile_metrics` also gets `_p50`, `_p95`, and `_p99`. The p95 needs 20 samples and the p99 needs 100 samples, unless the manifest sets other minimums. A percentile with too few samples is omitted and the review says so.

The claim rests on one `primary_metric` (default `median_ms`). It must have a `lower_is_better` or `higher_is_better` direction. Stability is judged for that metric. Every other metric shows its own delta and outcome (`better`, `worse`, `within_range`, `not_assessed`, `direction_mismatch`). ERA never combines metrics into one score. A worse side metric does not change the claim.

A workload with telemetry must also match on `execution.hardware_fingerprint`, `execution.concurrency`, and `execution.batch_size`. The manifest can waive one through `non_binding_dimensions`.

The vector records the telemetry file hash in `raw_evidence_refs` and the tool's scope in `measurement_scope`.

## Sample Policy, Uncertainty, and Energy (WP08)

A workload can set `evaluation.sample_policy`:

- `warmup_iterations` (0 to 20): the runner executes these runs and discards their output and timing. The review states how many were discarded.
- `min_samples`: a claim needs at least this many samples of the primary metric on both sides. Fewer samples give `no_claim_unstable`.
- `require_ci_separation`: an `improvement` or `regression` needs 95 percent intervals that do not overlap. Overlapping intervals, or a missing interval, give `no_claim_unstable`.

`era_core/eval_stats.py` computes a percentile bootstrap interval for each median (1000 resamples, 95 percent). The seed comes from the sample values, so the same samples always give the same interval. It needs 5 samples. With fewer, the vector records why the interval is omitted. Timing samples use whole milliseconds, so a very fast command has a coarse interval.

Energy metrics are `energy_joules`, `energy_per_token_j`, and `tasks_per_joule`. The manifest must declare `telemetry_policy.energy_scope`: `gpu_counter_only`, `cpu_package`, or `system_wall`. The telemetry file must report the same scope. A missing or different scope leaves the energy metrics out and the review names the problem. Every energy metric carries its scope, and the review prints the scope label. `gpu_counter_only` and `cpu_package` are labelled "Not wall power". A comparison must match on `execution.energy_scope`, so a GPU counter is never compared with a wall meter.

## Judge Audit (WP09)

ERA never calls a judge. An external harness writes a `JudgeEvidence.v1` file into the target tree. Each item has the verdict from both presentation orders (`winner_ab`, `winner_ba`, mapped back to `candidate`, `baseline`, or `tie`). Some items also carry a `human_label`. That subset is the calibration set.

A workload lists judge-derived metrics in `quality_gate_policy.judge_policy.judge_metrics`. Each one needs a quality floor. `era_core/eval_judge.py` writes a `JudgeAuditArtifact.v1` with:

- position consistency: the share of paired items where both orders give the same verdict;
- human agreement and Cohen's kappa on the calibration set (an inconsistent judge verdict counts as a miss);
- family separation: the judge model family must differ from the subject family;
- every disagreement (position flips, human disagreements, unpaired items), listed and never averaged away. The list stops at 50 entries and the total stays exact.

The status is `passed`, `failed`, `unproven`, or `invalid`. Too few items or labels, or an unknown family, give `unproven`. A missed threshold or a shared family gives `failed`.

A judge metric counts toward the quality gate only when the audit passed. Otherwise ERA removes it from the results and the gate is `unproven`, with the reason named. A hard floor that fails still gives `failed`. A high judge score cannot offset a failed hard floor.

The artifact has `authority: evidence_only`. The validator rejects any other value. Validation also recomputes the audit status from its numbers, so a forged `passed` fails. The hash chain and the review include the audit.

## Agent Efficiency (WP10)

ERA does not run an agent. An external harness runs the tasks and writes an `AgentRunEvidence.v1` file into the target tree. Each task has `success`, `steps`, `tool_calls`, `input_tokens`, `output_tokens`, `wall_time_ms`, and optionally `api_cost_usd` and `energy_joules`. A workload names the file in `evaluation.agent_policy.agent_evidence_path`.

An agent workload uses `subject_kind: "agent"`. Its `subject_identity` must name `agent_revision`, `model_lane`, `tool_policy_hash`, `prompt_program_hash`, `step_budget`, and `token_budget`. These fields, plus hardware, concurrency, and batch size, are required comparison dimensions. A different tool policy is incomparable.

`era_core/eval_agent.py` writes these metrics into the vector. Only declared metrics appear. A metric with missing inputs is left out and the review names the problem.

| Metric | Meaning |
|---|---|
| `task_success_rate` | successes divided by tasks. Also merged into the quality gate results, so a floor on it applies. |
| `steps_per_task`, `tool_calls_per_task`, `tokens_per_task`, `wall_time_ms_per_task` | median over all tasks |
| `api_cost_usd_per_successful_task` | total cost of all tasks divided by the number of successes. Failed tasks still cost money. Needs a cost on every task. |
| `joules_per_successful_task` | total energy divided by the number of successes. Needs energy on every task and a matching declared `energy_scope`. |

The success rate has a Wilson interval. The other medians have a bootstrap interval. The ratio metrics have a bootstrap interval that resamples whole tasks. Task-to-task spread is not measurement noise, so agent metrics are marked `task_level` and stability rests on `min_samples` and interval separation.

An agent that is cheaper because it fails gets `quality_blocked`. Quality is checked before efficiency. ERA reports each metric on its own row and computes no promotion score.

## Isolation Receipt (WP11)

Operator ruling 2 names `era_core/sandbox.py` as the authorized isolation provider. Each opted-in workload gets an `IsolationReceipt.v1` next to its fingerprint. The receipt records the sandbox, backend, network, and target filesystem that the run had, plus the trust attestation and the read-only scope. It states the limits of a contained run: it is not a full jail, and ERA does not certify that a workload is safe.

A workload requires isolation when its `subject_kind` is `agent` or its `evaluation.workload_traits` lists `agentic`, `mcp_tools`, `generated_code`, `external_repo`, or `untrusted`. No manifest field turns a required run off. A required run is `satisfied` only when the sandbox is `contained`, the network is `isolated`, and the target filesystem is `overlay_protected`. Otherwise it is `unsatisfied`.

An `unsatisfied` receipt blocks every claim except a quality outcome. The claim is `evidence_blocked` with the reason named, and the review says no claim was made. A trusted-target run without containment cannot make a promotion-capable claim for an agent.

Validation checks that the receipt matches the fingerprint's execution identity, that its requirement matches the manifest, that its status follows from its posture, and that the comparison records the same status.

Every comparison for an opted-in workload must now match on `execution.sandbox`, `execution.network`, and `execution.target_filesystem`. A contained run and an uncontained run never compare as equal (operator ruling 3).

## Evaluation Export (WP12)

A run with an opted-in workload writes `evaluation_export.json`. It is an `era_evaluation_export` v1 artifact: the shared envelope with the admitted payload. `forge_contract_core` admitted the family on 2026-09-30 (RFC-ERA-EVAL-01). ERA is the only producer.

The payload summarizes each workload's claim, gates, metrics, baseline, blocked reasons, and artifact hashes. It holds hashes and statuses only. Its `authority` text is fixed: ERA evidence, not canonical truth. The `evidence_hash_chain` lists the export as `evaluation_export`, by payload digest.

`era_core/eval_contract_export.py` applies the contract's rules:

- A measured non-count quantity is a canonical decimal string. There is no exponent, no leading `+`, no unneeded zero, and no negative zero. A count stays an integer. No JSON float appears anywhere.
- `workloads[]` is sorted by `workload_id`. A set-like array is sorted and has no duplicate. A long reason is cut to 1024 characters. More than 64 reasons are replaced by a count.
- `payload_digest` is the self-digest under `forge.rfc8785-jcs-sha256.v1` with domain `forge:era-evaluation-export:v1`. The digest field is excluded from the hashed projection.
- The attesting user, `executes_target_code`, and local paths are dropped.

The envelope `signature` is `unsigned:<payload digest>`. It is a digest reference, not a cryptographic signature, because ERA holds no signing key.

`era_core/eval_export.py` rebuilds the artifact from the run folder during validation and rejects any difference. A run without an opted-in workload has no export.

DataForge Local intake and the Forge_Command route are separate work. They consume the admitted contract. See `docs/eval/BDS-ERA-EVAL-v0.1_WP12_INTERFACE.md`.

## Baseline Snapshot (operator decision 4)

When a comparison names a baseline run, the newer run stores `baseline_snapshot.json` (`BaselineSnapshot.v1`). It copies the baseline's fingerprint, quality gate, and metric vector, and records their hashes. The snapshot is in the hash chain and in the evaluation export as `baseline`.

Validation proves the baseline from the snapshot: its evidence validates, its quality gate passed, its fingerprint is comparable under the manifest dimensions, and the comparison's baseline value matches. The baseline run folder is not needed. If it still exists, it must match the snapshot, so an edited folder cannot pass beside a good snapshot. `reconstruct_claim(..., from_snapshot=True)` rebuilds the claim without any sibling run folder.

A run made before this change has no snapshot and still needs its baseline folder.

## Publishing to DataForge Local (ERA-PUB-01)

Company Core Six, principle 6: automate up to the decision. After `era run`, ERA copies the run's `evaluation_export.json` into the inbox that DataForge Local scans. DataForge Local stores it, Forge_Command shows it, and the operator decides. Nothing here approves or acts.

`era_integrations/inbox_publish.py` does the copy.

- **Location.** `DFL_ERA_DROP_DIR`, default `~/.dataforge-local/era-inbox`. This is the shared convention with DataForge Local.
- **ERA never creates the inbox** and never writes to DataForge Local itself. If the directory is missing, ERA skips and says so.
- **Fail closed.** ERA skips a symlinked inbox, an inbox owned by another user, and a group- or world-writable inbox. The envelope `signature` is an unsigned digest reference, so the inbox permission is the producer check on the other side. ERA does not publish into a directory that would weaken it.
- **How.** ERA writes a hidden temporary file (mode 0600), flushes it, and renames it to `era_evaluation_export.<run_id>.json`. DataForge Local ignores the temporary name. Publishing the same run again gives the same file.
- **Size.** ERA skips an export over 256 KiB (DataForge Local's store limit) and reports it.
- **A skip never fails the run.** The run's own evidence is complete without it. `era run` prints the outcome on stderr. Stdout is still the run path.
- **Receipt.** `publish_receipt.json` in the run folder records the outcome. It is an operational receipt outside the evidence hash chain.
- **Off switch.** `era run --no-publish`. Library callers of `execute_run` do not publish. Only the command does. The test session points the inbox at a path that does not exist.


---

            # Runtime Boundary

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            ERA runs locally through the Python CLI and writes under `ERA/artifacts/era-runs/<run_id>/`.

ERA never writes inside the evaluated target repository. Changed-file and full-run modes are evidence collection modes, not remediation authority.

---

            # Dependencies

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            ERA is a Python package with CLI entrypoints under `era_cli/` and implementation modules under `era_core/`.

Dependency and tool truth must be read from `pyproject.toml`, workload manifests under `config/workload_manifests/`, and executable test results.

---

            # Governance

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            ERA remains an assurance subsystem, not a patching subsystem. Findings and projections require operator review before any downstream action.

Redundancy exceptions are operator-approved review context; they are not parser instructions to delete or suppress evidence.

---

            # Verification

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            Common operator commands are:

```bash
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode full
python -m era_cli report --latest
python -m era_cli validate --latest
```

Unit tests live under `tests/` and should be run before changing artifact or contract behavior.

## Evaluation Proving Run (BDS-ERA-EVAL-v0.1 GATE-06)

Run `python3 scripts/eval_proving_run.py` to prove the quality-gated claim semantics. The script runs seven scenarios through the real run path with local sleep commands. It calls no model, provider, agent, or network. It checks that each scenario reaches its expected claim, that the run validates, and that `era_core/eval_reconstruct.py` rebuilds the same claim from the artifacts on disk. Details and the committed receipt are in `docs/eval/BDS-ERA-EVAL-v0.1_GATE-06_proving_run.md`.

---

            # Appendices

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            Supporting authored material lives in `docs/ERA_Plan_Set_MD/`.

This system reference captures current repo boundaries and should be rebuilt whenever ERA contract, lane, or CLI behavior changes.
