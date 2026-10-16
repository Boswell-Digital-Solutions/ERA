BDS-ERA-EVAL-v0.1 — 04 Core Contracts, Schema, and Provenance Model
Section 04 purpose: define the minimal local contract pack required to prove quality-gated efficiency without replacing ERA's existing evidence chain.


Contract pack for ERA-EVAL-01
EvaluationConfigFingerprint.v1
QualityGateArtifact.v1
MetricVector.v1
QualityEfficiencyComparison.v1
EfficiencyWorkloadManifest.v2 extension semantics


EvaluationConfigFingerprint.v1
Purpose: bind quality and efficiency evidence to the exact configuration that produced it.
Required identity fields:
schema_version
fingerprint_id
run_id
repo_id
workload_id
subject_kind
source_commit_sha
runtime_identity
evaluation_identity
execution_identity
created_at
sha256


Conditional subject identity fields
For a repository command: executable/tool identity, command digest, cwd scope, relevant environment fingerprint.
For a local model: model ID, model revision/weights digest where available, quantization, runtime engine/version, context length, prompt/template hash, sampler/generation settings.
For a provider model: provider, model identifier/revision where exposed, request policy version, prompt/template hash, generation settings, region/endpoint class when it can affect latency.
For an agent: agent/harness revision, model/provider lane, tool-policy hash, prompt/program hash, step/token budget profile, fixture/eval suite identity.


Evaluation identity
suite_id
suite_version
dataset_or_fixture_hash
scorer_id
scorer_version
harness_id
harness_version
split_or_holdout_class
quality_floor_policy_id


Execution identity
hardware_fingerprint when a metric is hardware-bound
OS/runtime version
concurrency
batch_size
network_mode where relevant
resource-policy identifier where relevant


Fingerprint rule
The fingerprint hash covers the normalized comparison-relevant configuration object. A QualityGateArtifact and MetricVector used in the same claim must reference the same fingerprint ID and digest.


QualityGateArtifact.v1
Required fields:
schema_version
quality_gate_id
run_id
repo_id
workload_id
config_fingerprint_id
config_fingerprint_sha256
suite_id
suite_version
metric_results
quality_floors
gate_status
failure_reasons
sample_count
uncertainty_summary if available
raw_evidence_refs
created_at
sha256


gate_status values:
passed
failed
unproven
invalid


MetricVector.v1
Purpose: preserve multiple efficiency/resource measurements without collapsing them into one score.
Required fields:
schema_version
metric_vector_id
run_id
workload_id
config_fingerprint_id
metrics
sample_count
variance_or_uncertainty
measurement_scope
raw_evidence_refs
created_at
sha256


Initial v0.1 metric support may contain only duration_ms/median_ms plus existing variance classification. Later adapters may add TTFT, TPOT/ITL, tokens_per_second, throughput, RAM, VRAM, joules, joules_per_token, cost, steps, tool calls, and token counts.


QualityEfficiencyComparison.v1
Required fields:
schema_version
comparison_id
run_id
workload_id
candidate_fingerprint_id
baseline_fingerprint_id
quality_status
comparability_status
efficiency_status
claim_status
comparison_dimensions
metric_deltas
blocked_reasons
baseline_run_id
candidate_run_id
created_at
sha256


comparability_status:
comparable
incomparable
unknown


efficiency_status:
improvement
regression
within_range
unstable
not_evaluated


claim_status:
permitted
quality_blocked
quality_unproven
incomparable
evidence_blocked


EfficiencyWorkloadManifest.v2
v1 manifests remain valid for generic command timing. v2 adds optional quality_gate_policy, config_fingerprint_policy, metric declarations, required comparison dimensions, warmup/sample policy, and subject_kind. An ERA v1 workload may never be silently upgraded into an AI-quality claim.


Provenance chain
Existing ERA chain remains:
raw evidence → ToolRawArtifact.v1 → ToolNormalizedResult.v1 → LaneFindingDraft.v1 → ERAFinding.v1 → ERAScore.v1 → review artifact.


New evaluation artifacts join the chain as evidence-bearing siblings referenced by normalized results and findings. They do not bypass raw evidence or replace ERAFinding/ERAScore.


Hash rule
Any mismatch among fingerprint hash, quality artifact reference, metric vector reference, baseline identity, or comparison artifact hash fails validation and blocks the claim.