BDS-ERA-EVAL-v0.1 — 05 Quality-Gated Evaluation Mechanism
Section 05 purpose: specify the exact decision path ERA uses before making an efficiency improvement or regression claim.


Current-state problem
ERA-01C correctly requires a workload, successful execution, stable timing, and a prior baseline before making a regression/improvement claim. Current comparison is primarily median wall-clock timing plus variance and threshold logic. This is sufficient for generic command regression proof but insufficient for AI/model/agent optimization because a faster candidate can be less capable.


Core mechanism
Step 1 — build the candidate EvaluationConfigFingerprint.
Step 2 — locate the workload's declared quality policy.
Step 3 — produce or resolve the QualityGateArtifact for the same candidate fingerprint.
Step 4 — reject claim formation if quality is failed, unproven, invalid, or points at another fingerprint.
Step 5 — select a baseline using required comparison dimensions, not merely latest prior run.
Step 6 — classify baseline comparability.
Step 7 — construct the candidate MetricVector and baseline MetricVector.
Step 8 — apply current variance/stability rules plus any later statistical policy.
Step 9 — compute metric deltas only when quality and comparability gates permit.
Step 10 — emit QualityEfficiencyComparison.v1 and promote any actionable regression through the existing ERA normalization/finding chain.
Step 11 — render the comparison basis in review.md so no 'improvement' label appears without quality status, fingerprint match, baseline source, and stability status.


Minimal first-slice decision table
quality=passed + comparable + stable + delta exceeds improvement threshold → improvement / claim permitted.
quality=passed + comparable + stable + delta exceeds regression threshold → regression / claim permitted.
quality=passed + comparable + stable + delta inside thresholds → within_range / claim permitted.
quality=passed + comparable + unstable → unstable / no improvement-regression claim.
quality=failed → quality_blocked regardless of speed.
quality=unproven → quality_unproven regardless of speed.
quality=invalid → evidence_blocked.
fingerprint mismatch on a required dimension → incomparable.
missing baseline → no_baseline / no claim.
tampered or stale evidence → evidence_blocked.


Baseline matching
For ERA-EVAL-01, the baseline selector must match:
repo_id
workload_id
subject_kind
source or subject revision fields declared required
evaluation suite ID/version
dataset/fixture hash
scorer/harness identity where required
quality-floor policy
comparison-relevant runtime/generation parameters
hardware fingerprint for hardware-bound timing/resource metrics
concurrency and batch size for concurrency-sensitive metrics


No implicit normalization
A quantization change, runtime engine change, model revision change, prompt-template change, dataset hash change, scorer change, hardware change, concurrency change, or other declared comparison dimension cannot be waved away because both runs succeeded. Either the manifest explicitly declares that dimension non-binding for a specific metric or ERA marks the comparison incomparable.


Metric direction
Each metric declaration must say whether lower_is_better, higher_is_better, target_range, or informational_only. ERA must not assume direction from a metric name.


Quality floors
Quality floors may be deterministic pass/fail, threshold metrics, schema compliance, task success, or a bounded vector of requirements. Failure of any declared hard quality floor blocks the efficiency claim.


Metric vectors
Do not compute one universal combined efficiency score in v0.1. Review artifacts show quality outcome and each declared metric delta independently.


First proof
The first proof should use deterministic test fixtures that simulate:
baseline quality pass + stable timing;
candidate quality pass + faster timing;
candidate quality fail + faster timing;
candidate config mismatch;
candidate missing quality artifact;
candidate unstable timing.


This proves semantics without cloud spend or model nondeterminism.


Later adapter boundary
TTFT/TPOT, token throughput, RAM/VRAM, energy, agent token/cost/step measures, and public/private benchmark harnesses plug into MetricVector and QualityGateArtifact. ERA consumes their evidence; it does not reimplement their engines.