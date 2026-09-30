# BDS-ERA-EVAL-v0.1 — WP12 Interface (durable and UI integration)

Date: 2026-09-30
Status: ERA side built. Downstream side needs operator decisions (see the last section).

## What WP12 asks for

Plan section 08: "DataForge Local persistence and Forge_Command review surfaces after local artifact semantics stabilize."

## What the recon found

- **Forge_Command** takes ERA evidence through the Centipede inbox (`~/.forge-command/centipede-inbox/`). It imports a `CentipedeIntakeBundle` and shows it as an evidence-only incident on `/self-healing`. The bundle shape belongs to `forge_contract_core` and to `src-tauri/src/centipede/intake.rs`. Evaluation claims are not findings, so they do not fit that shape.
- **DataForge Local** has no ERA or evaluation ingestion surface. Its FailureForge router has no ERA endpoint. Its authority is durable local evidence storage.
- **forge_contract_core** owns shared cross-repo contracts. Plan AUTHORITY_GAP-01 says a contract that another repo must consume needs promotion first. Promotion is a separate authorization (decision D3).

So ERA cannot finish WP12 alone without deciding another repo's contract. ERA does not do that.

## What ERA built (this change)

`ERAEvaluationExport.v1` is written to `evaluation_export.json` in each run that has an opted-in workload. It is the producer interface. It is the same idea as the Centipede inbox: the producer side is a file with a clear contract, and the consumer decides how to take it.

The export summarizes files that already exist in the run folder.

| Field | Meaning |
|---|---|
| `run_id`, `repo_id`, `commit_sha`, `run_status` | run identity |
| `efficiency_lane_classification` | the lane class from the ERA score |
| `execution_posture` | sandbox, backend, network, target filesystem, trust |
| `workloads[]` | one entry per opted-in workload |
| `workloads[].claim_status`, `quality_status`, `comparability_status`, `efficiency_status`, `isolation_status` | the claim and its gates |
| `workloads[].primary_metric`, `metrics`, `metric_deltas`, `measurement_scope` | each metric on its own row, with units, directions, and energy scope |
| `workloads[].fingerprint_id`, `config_digest`, `baseline_run_id`, `baseline_fingerprint_id` | identity and baseline |
| `workloads[].blocked_reasons`, `baseline_rejection_reasons` | why no claim, and why runs were rejected as baselines |
| `workloads[].judge_audit_status` | the judge audit status, when a judge policy exists |
| `workloads[].baseline` | the baseline snapshot summary: run, fingerprint, quality status, metrics, part hashes, snapshot digest |
| `workloads[].artifacts` | path and hash of each evaluation artifact |
| `authority` | fixed text: ERA evidence only, not canonical truth |
| `consumer_contract_status` | `local_to_era`. It says the contract is not promoted. |
| `created_at`, `sha256` | the run completion time and the canonical hash |

It carries no raw evidence, no command output, no quality-results file, and no judge or agent evidence. It holds hashes and statuses only.

**Validation.** `validate_run_dir` rebuilds the export from the run folder and rejects any difference. It also checks the authority text, the hash chain entry, and that a run with no opted-in workload has no export. A forged claim in the export fails the rebuild, even if the forger reseals it and refreshes `hashes.json`.

**Legacy runs.** A run with no opted-in workload writes no export and validates as before.

## Decisions for the operator

These need your answer before any change outside ERA.

1. **Contract promotion.** Promote `ERAEvaluationExport.v1` to `forge_contract_core`? Plan D3 kept it local until a cross-repo need showed up. This is that need. Promotion is a change in another repo and needs its own authorization: the schema, the validator, and an RFC.
2. **DataForge Local persistence.** Add an ingestion endpoint and a table for the export in DataForge Local? Or use a drop directory like the Centipede inbox and let DataForge Local pick files up? The drop directory keeps ERA from writing into another system. I recommend the drop directory first.
3. **Forge_Command review surface.** Add a read-only evaluation review route in Forge_Command that shows claims, gates, and blocked reasons? Or extend the `/self-healing` incident view? Evaluation claims are not incidents, so I recommend a separate read-only route. Forge_Command keeps the operator authority. It must never turn a claim into an action.
4. **Retention.** The stale-baseline check means a run needs its baseline run folder. DataForge Local persistence could snapshot the baseline evidence, so old run folders can be archived. Decide whether persistence must keep the baseline chain.

## Authority check

ERA still finds, measures, proves, and reports. The export gives no approval, promotion, routing, or mutation authority. No other repository changed.
