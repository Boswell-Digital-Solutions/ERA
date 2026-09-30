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

These modules are not yet connected to the efficiency lane. Legacy `EfficiencyWorkloadManifest.v1` behavior is unchanged.
