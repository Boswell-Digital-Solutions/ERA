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
