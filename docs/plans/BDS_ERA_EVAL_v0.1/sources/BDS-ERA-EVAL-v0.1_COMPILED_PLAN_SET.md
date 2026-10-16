BDS-ERA-EVAL-v0.1 — Compiled Plan Set
Plan ID: BDS-ERA-EVAL-v0.1
Title: ERA Quality-Gated Evaluation Expansion
Lifecycle: proposed
Authority: Plan candidate only; no repository mutation. CP0/WP00 requires separate explicit authorization.
Decision owner: Charlie Boswell, Sole BDS Operator
Prepared: Sep 30, 2026 America/Chicago
Canonical Drive destination: /Forge/Plans/BDS-ERA-EVAL-v0.1
Compilation: 00–09
Compilation mode: hand-maintained under BDS-PSS-001; component edits must be mirrored into this compiled artifact until build tooling exists.


00 — PLAN SET INDEX


Plan ID
        BDS-ERA-EVAL-v0.1
        Title
        ERA Quality-Gated Evaluation Expansion
        Lifecycle
        proposed
        Authority
        Plan candidate only; no repository mutation. CP0/WP00 requires separate explicit authorization.
        Decision owner
        Charlie Boswell, Sole BDS Operator
        Prepared
        Sep 30, 2026 America/Chicago
        Parent / extension target
        Existing ERA-01C / ERA-02 / ERA-03 roadmap; related BDS-GRI-01
        Proposed canonical owner
        Boswell-Digital-Solutions/ERA; fresh source lock required at implementation start
        Primary candidate consumer
        Boswell-Digital-Solutions/ERA; later Forge_Command/DataForge through existing boundaries
        Canonical Drive destination
        /Forge/Plans/BDS-ERA-EVAL-v0.1
        Compilation
        00–09 → BDS-ERA-EVAL-v0.1_COMPILED_PLAN_SET.md
        Read order
00 Index → 01 Rulings → 02 Authority → 03 Protocols → 04 Contracts → 05 Mechanism → 06 Semantics → 07 QA → 08 Work Packages → 09 Operator Review.




Source basis
Operator-supplied Gemini research memo on AI accuracy/efficiency measurement.
Operator-supplied Grok research memo on production-grade quality-gated evaluation.
Current Boswell-Digital-Solutions/ERA repository review, anchored during planning to master head 13180a8837590476e3c8ff6f115f8a3c571b768d.
BDS-PSS-001 plan-set structure standard and current ERA manifest/charter/roadmap.




Current-state anchor
ERA already provides accuracy, redundancy, and efficiency lanes; raw → normalized → draft → finding → score provenance; evidence hash validation; workload manifests; baseline timing comparison; trusted-target fail-closed execution; and Centipede/Self-Healing export boundaries.
The current efficiency proof is primarily wall-clock baseline regression detection. This plan adds exact-configuration identity and a quality gate before richer AI-system measurements are admitted.




Plan objective
Prove the smallest governance-safe change that prevents ERA from calling a configuration more efficient when the exact configuration fails its declared quality floor or is not comparable to the baseline.




Authorization note
This lifecycle is proposed. No code, schema promotion, model call, deployment, or runtime change is authorized by creation of this plan set.


────────────────────────────────────────


01 — BINDING RULINGS AND NON GOALS


BDS-ERA-EVAL-v0.1 — 01 Binding Rulings and Explicit Non-Goals
Section 01 purpose: freeze the decisions that govern the ERA evaluation expansion before any implementation work.




Binding rulings
1. ERA remains an assurance subsystem. The existing doctrine remains controlling: ERA finds, measures, proves, and reports; ERA does not fix, approve, promote, route models, or mutate production state.
2. The next evaluation evolution is quality-gated efficiency. ERA must not claim that a candidate configuration is more efficient unless the candidate satisfies the declared quality floor on the same pinned configuration used for the efficiency measurement.
3. Baseline comparison becomes configuration-aware. A prior run is not a valid efficiency baseline merely because it targets the same repository and workload name. Required comparability dimensions must match.
4. ERA reports metric vectors, not one universal intelligence or efficiency scalar. Existing ERAScore.v1 remains a classification/count summary and must not become an optimization objective that can hide trade-offs.
5. Missing quality evidence is not a pass. Missing or invalid quality evidence produces quality_unproven or evidence_blocked; it cannot produce improvement.
6. Configuration mismatch is not regression or improvement. It is incomparable until an explicitly authorized comparison policy says otherwise.
7. Hard governance and evidence-integrity gates override performance gains.
8. Local contracts are permitted for the first bounded proof. Cross-repo schema promotion remains subject to forge-contract-core authority.
9. The first proving slice uses deterministic fixtures and trusted in-house execution. Live model, agent, external API, or tool-rich evaluation is held until the relevant execution-isolation and provider/runtime receipts are available.
10. The research is evidence, not authority. The Gemini memo contributes the richer telemetry vocabulary; the Grok memo contributes the quality-floor-first and same-config comparison pattern. ERA's canonical repo contracts and BDS governance remain controlling.




Initial implementation target
ERA-EVAL-01 — Comparable Configuration + Quality-Gated Efficiency Proof.




The first proof introduces a configuration fingerprint, a quality-gate artifact, comparable-baseline selection, and a cross-lane claim gate. It does not require live model calls, DataForge persistence, Forge_Command UI, or a new sandbox implementation.




Explicit non-goals
This plan does not authorize automatic model selection or ranking.
This plan does not make ERA a benchmark provider, prompt optimizer, inference engine, router, model trainer, profiler, or load generator.
This plan does not reimplement MLPerf, Inspect, lm-eval, vLLM-bench, Nsight, NVML, or model-serving engines.
This plan does not authorize autonomous repair, auto-fix, auto-promotion, or patch application.
This plan does not authorize hidden-eval generation or custody changes in the first proving slice.
This plan does not move canonical shared-schema authority out of forge-contract-core.
This plan does not move operator authority out of Forge_Command.
This plan does not require DataForge Local for the first local proof.
This plan does not treat LLM-as-judge output as ground truth.
This plan does not require wall-power instrumentation, MFU/MBU profiling, TTFT/TPOT adapters, energy measurement, or agent economics in ERA-EVAL-01.
This plan does not weaken the current --trusted-target fail-closed gate or the read-only-to-target posture.




Research adoption boundary
Adopt now: exact-configuration pinning; quality floors; metric vectors; quality-gated efficiency claims; comparable baselines; explicit unproven/incomparable states; stronger repeatability metadata.
Stage next: TTFT, TPOT/ITL, tokens per second, RAM/VRAM, p50/p95/p99 where appropriate, confidence intervals, energy per token, successful-task-per-joule, cost per successful agent task, private/rotating eval sets, judge audits.
Defer to external adapters: microarchitectural profiling, quantization algorithms, speculative-decoding implementation, serving disaggregation, physical AC instrumentation, and public benchmark implementation.




Plan-creation authority
Creation of this plan set establishes a reviewable proposed plan only. It authorizes no repository mutation. The operator review packet may separately authorize CP0/WP00 read-only source lock.


────────────────────────────────────────


02 — AUTHORITY BOUNDARY AND GAPS


BDS-ERA-EVAL-v0.1 — 02 Authority Boundary and AUTHORITY_GAP Conditions
Section 02 purpose: bind the new evaluation mechanics to existing BDS authority and stop if ownership is ambiguous.




Authority map
ERA owns local evaluation execution receipts, local accuracy/redundancy/efficiency evidence, normalization, comparison evidence, finding classification, evidence hashing, and review artifacts.
Forge_Command owns operator review and final authorization surfaces.
forge-contract-core owns shared cross-repo schemas, enums, validators, and promoted contract authority.
DataForge Local owns durable evidence persistence once the later persistence slice is authorized.
NeuroForge owns cloud/provider routing and provider/model invocation policy and receipts when cloud evaluation is eventually admitted.
NeuronForge owns local model runtime qualification where local model measurements are performed.
Hephaestus owns model-engineering and shaping preparation; ERA may evaluate resulting candidates but cannot shape or promote them.
forge-smithy / SMITH owns governed mutation and patch-candidate boundaries after operator authorization.
Centipede may consume and reconcile ERA evidence under its existing boundary; it does not become evaluation authority.




ERA invariant
ERA may determine whether evidence supports an evaluation claim. It may not decide that a model, agent, configuration, patch, or runtime becomes the production champion.




AUTHORITY_GAP-01 — shared contract promotion
Status: OPEN by design for first slice.
Local EvaluationConfigFingerprint.v1, QualityGateArtifact.v1, MetricVector.v1, and QualityEfficiencyComparison.v1 may be proven inside ERA. If another repository must produce or consume the canonical contract directly, promotion to forge-contract-core is required before cross-repo reliance.




AUTHORITY_GAP-02 — execution isolation provider
Status: OPEN for tool-rich/agent evaluation; not blocking deterministic trusted-target fixture proof.
ERA currently has no sandbox and truthfully records that limitation. ERA-EVAL-01 may use trusted in-house deterministic fixtures under the existing --trusted-target gate. Agentic, MCP-tool, external-repo, generated-code, or untrusted evaluation must not be admitted as a promotion-capable proof until an authorized isolation provider and receipt shape are bound.




AUTHORITY_GAP-03 — durable eval-corpus custody
Status: OPEN for private/rotating evaluation.
The first slice may use versioned local fixtures committed to ERA tests. Private golden sets, rotating holdouts, and hidden promotion fixtures require a separately governed custody location and access policy. ERA may record dataset hashes and references but should not silently become the secret-corpus authority.




AUTHORITY_GAP-04 — hardware identity normalization
Status: OPEN for heterogeneous hardware comparisons.
ERA-EVAL-01 will fail closed for hardware-bound efficiency comparison when required hardware fingerprint fields differ. Cross-hardware normalized claims require a later explicit policy and are not inferred from raw timing.




AUTHORITY_GAP-05 — judge calibration authority
Status: HELD.
LLM judges are optional later instrumentation. No judge result may control a hard gate until JudgeAuditArtifact semantics, AB/BA ordering, human calibration, and family-separation policy are authorized.




Collision decisions
No new control plane is created.
No new canonical memory authority is created.
No new mutation authority is created.
No new provider routing authority is created.
No new model-promotion authority is created.
No existing ERA lane is removed; the evaluation expansion composes with the accuracy and efficiency lanes.




Fail-closed rule
If a required authority owner cannot be resolved at implementation time, the affected work package stops and emits a remediation packet rather than substituting ERA as the missing authority.


────────────────────────────────────────


03 — GOVERNING PROTOCOL BINDING


BDS-ERA-EVAL-v0.1 — 03 Governing-Protocol Binding
Section 03 purpose: state which existing canonical rules govern this plan and how conflicts are resolved.




Structural authority
BDS-PSS-001 — BDS Plan Set Structure Standard governs this plan set's 00–09 component structure, compiled artifact, lifecycle vocabulary, manifest siblings, and verification expectations.




Documentation authority
BDS-DOC-001 governs canonical documentation posture where it applies. Repository implementation must preserve ERA's doc/system parity and must not introduce hand-edited generated artifacts when a canonical generation path exists.




Repository authority
Boswell-Digital-Solutions/ERA repo.manifest.yaml is the current repository authority declaration.
Current declared ERA authority role: local_verification_and_evidence_production.
Current declared non-ownership includes patches/merges/remediation, approval/promotion/operator decisions, canonical ecosystem memory, shared cross-repo schema doctrine, durable reconciliation authority, model routing/candidate generation, and command-plane operator authority.




ERA-local governing sources
README.md defines the current execution posture and --trusted-target requirement.
docs/ERA_Plan_Set_MD/01-ERA-Executive-Charter.md defines the ERA doctrine and lane purposes.
docs/ERA_Plan_Set_MD/04-Contracts-Artifacts-and-Evidence-Model.md defines the current raw → normalized → draft → finding → score evidence chain.
docs/ERA_Plan_Set_MD/09-Implementation-Roadmap-and-Slices.md defines the existing ERA roadmap and the ERA-01C efficiency proof posture.
era_core/efficiency.py and era_core/review_writer.py are implementation evidence for current baseline selection and efficiency classification; they are not policy authority beyond the canonical docs and manifest.




Related plan lineage
BDS-GRI-01 is related evidence because it requires champion/challenger comparability, hard gates, fixed budgets, and visible/hidden evaluation separation. This ERA plan does not subordinate ERA to GRI and does not grant GRI promotion authority. ERA may later provide evaluation evidence consumed by GRI or AAR.




Research-source treatment
Gemini research memo: use for metric vocabulary and future instrumentation options such as TTFT, TPOT/ITL, throughput, tail latency, resource use, energy, sparse utilization, and phase-aware prefill/decode measurements.
Grok research memo: use for the primary architecture rule: set a quality floor first, then optimize latency/energy/cost on the exact pinned configuration; version harness/configuration; report vectors; use private workloads; add uncertainty; audit judges.
Neither research memo can override BDS authority, repository contracts, operator decisions, or source truth.




Conflict precedence
1. Explicit operator authorization.
2. Canonical BDS protocols and admitted authority records.
3. Repository manifest and canonical ERA documentation.
4. Source-locked implementation behavior.
5. This plan set.
6. Research memos and external benchmark methodology.




Protocol compliance test
GATE-00 must record the exact current versions/provider IDs of governing protocols and verify no newer canonical ERA plan supersedes the assumptions above. A conflict stops implementation planning at the affected boundary.


────────────────────────────────────────


04 — CONTRACTS AND PROVENANCE MODEL


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


────────────────────────────────────────


05 — QUALITY GATED EVALUATION MECHANISM


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


────────────────────────────────────────


06 — DECISION SEMANTICS


BDS-ERA-EVAL-v0.1 — 06 Decision Semantics
Section 06 purpose: define how ERA labels evidence so operators and downstream systems cannot mistake speed, quality, or comparability for authorization.




Evidence states
quality_status: passed | failed | unproven | invalid.
comparability_status: comparable | incomparable | unknown.
efficiency_status: improvement | regression | within_range | unstable | not_evaluated.
claim_status: permitted | quality_blocked | quality_unproven | incomparable | evidence_blocked.




Meaning of 'improvement'
ERA may use the word improvement for a declared efficiency metric only when:
the candidate quality gate passed;
the quality and efficiency artifacts reference the same candidate fingerprint;
the baseline is comparable under all required dimensions;
both candidate and baseline evidence validate;
the measurement is stable under the active policy;
the metric direction is declared;
the delta crosses the manifest's improvement threshold.




Meaning of 'regression'
A regression is a comparable, evidence-backed worsening beyond the declared threshold. A quality failure is not reduced to an efficiency regression; it is quality_blocked and should remain visible as the controlling failure.




Meaning of 'incomparable'
Incomparable is a truthful outcome, not a system error. It means the evidence cannot support a fair baseline claim under the active comparison policy. ERA may still display the raw measurements side by side with a clear no-comparison label.




Meaning of 'quality_unproven'
No quality artifact, missing hard-floor result, mismatched fingerprint, or incomplete quality evidence prevents an efficiency improvement claim. 'No evidence of quality regression' must never be rewritten as 'quality passed.'




Existing ERA classifications
Existing lane classification values remain available for current workloads. ERA-EVAL-01 should add the smallest compatible classification surface needed for quality_blocked, quality_unproven, and incomparable behavior without breaking legacy generic timing workloads.




ERAScore rule
ERAScore.v1 remains a summary of classifications and evidence counts. It must not become a weighted aggregate that can offset a failed quality, security, authority, or evidence-integrity gate.




Operator decisions
ERA does not make accept/reject product decisions. It produces evidence classifications and review candidates. Forge_Command/operator actions remain outside ERA's own authority.




Downstream projection
A comparable efficiency regression with valid quality evidence may continue to qualify for the existing efficiency-regression review projection.
A quality failure may qualify for a separate future projection only after a bounded finding type and downstream mapping are explicitly authorized.
Incomparable, quality_unproven, unstable, or evidence_blocked states are evidence-only by default and must not trigger automatic remediation proposals.




Unknown state rule
Unknown required policy, missing required field, unrecognized comparison dimension, or unsupported metric direction fails closed to no claim.


────────────────────────────────────────


07 — QA AND VERIFICATION PLAN


BDS-ERA-EVAL-v0.1 — 07 QA and Verification Plan
Section 07 purpose: prove the new evaluation semantics fail closed, remain reproducible, and preserve ERA's evidence chain.




Verification layers
Contract validation.
Fingerprint determinism.
Quality-gate correctness.
Baseline-comparability correctness.
Metric/stability correctness.
Cross-artifact hash integrity.
Review rendering.
Backward compatibility for legacy EfficiencyWorkloadManifest.v1.
Read-only-to-target invariant.
Trusted-target execution gate.




Required positive regression cases
P01 same config + quality pass + stable faster candidate => improvement, permitted.
P02 same config + quality pass + stable slower candidate => regression, permitted.
P03 same config + quality pass + delta inside threshold => within_range, permitted.
P04 legacy v1 generic command workload continues current behavior when no quality policy is declared.
P05 repeated construction of an identical normalized config produces the same fingerprint hash.




Required negative regression cases
N01 faster candidate + quality failed => quality_blocked; no improvement claim.
N02 faster candidate + quality missing => quality_unproven.
N03 model/subject revision changes on a required dimension => incomparable.
N04 quantization changes on a required dimension => incomparable.
N05 prompt/template hash changes on a required dimension => incomparable.
N06 dataset/fixture hash changes => incomparable.
N07 scorer or harness version changes when declared binding => incomparable.
N08 hardware fingerprint changes for hardware-bound timing => incomparable.
N09 concurrency or batch changes for a sensitive metric => incomparable.
N10 candidate or baseline variance unstable => unstable; no improvement/regression claim.
N11 quality artifact references a different config fingerprint => evidence_blocked.
N12 metric vector references a different config fingerprint => evidence_blocked.
N13 tampered quality artifact hash => validate fails.
N14 tampered fingerprint object or stale digest => validate fails.
N15 baseline artifact exists but does not satisfy comparison dimensions => no comparable baseline.
N16 missing metric direction => evidence_blocked or no claim.
N17 unknown required comparison field => no claim.
N18 candidate command fails/times out => existing blocked/failure behavior remains controlling.
N19 untrusted target without explicit attestation => run refuses before execution and writes no false proof.
N20 read-only invariant failure/head change during run => no quality-efficiency claim.




Review artifact assertions
review.md must show candidate fingerprint ID.
review.md must show quality gate status.
review.md must show baseline run/fingerprint.
review.md must show comparability status and blocked reason.
review.md must show stability/uncertainty state.
review.md must show metric deltas separately.
review.md must never render 'improvement' without the gating context above.




Hash-chain assertions
New evaluation artifacts must be embedded or referenced in hashes.json/evidence chain using existing ERA conventions.
Validation must reject stale references, missing artifacts, mismatched run IDs, mismatched config hashes, and broken raw-evidence references.




Source-lock verification
GATE-00 records immutable ERA head, relevant file blob hashes, current tests, current manifest behavior, and current doc/plan authority. Tests are written against the locked baseline, not memory of the codebase.




First live proof gate
No live model/provider/agent run is required to close ERA-EVAL-01. After deterministic proof closes, a separate operator decision may authorize one local model/config pair to demonstrate a real quality-plus-latency comparison.


────────────────────────────────────────


08 — WORK PACKAGES AND GATES


BDS-ERA-EVAL-v0.1 — 08 Work Packages and Gates
Section 08 purpose: sequence implementation so the smallest semantics proof lands before richer telemetry, judges, agents, persistence, or UI work.




CP0 / WP00 — Read-only source lock
Scope: re-read current ERA master and canonical Drive plan/protocol sources; capture immutable head and file/blob evidence.
Required evidence: repo head, repo.manifest.yaml, README execution posture, efficiency.py, contracts.py, review_writer.py, validation.py, run.py, test_efficiency.py, Forge_Command workload manifest, current doc/system parity, current relevant plan docs.
GATE-00 PASS: no authority collision or contradictory newer implementation.
GATE-00 FAIL: stop with remediation packet. No runtime changes.




CP1 / WP01 — Local contract proof
Implement local dataclass/dict/schema validation for EvaluationConfigFingerprint.v1, QualityGateArtifact.v1, MetricVector.v1, and QualityEfficiencyComparison.v1.
Add deterministic canonical hashing.
Do not promote contracts to forge-contract-core yet.
GATE-01: positive and malformed fixtures validate/fail as expected; existing test suite remains green.




CP1 / WP02 — Fingerprint and comparability engine
Implement normalized comparison dimensions and baseline match policy.
Preserve current branch/baseline behavior for legacy generic workloads.
GATE-02: required mismatch cases produce incomparable, not improvement/regression.




CP2 / WP03 — Quality-gate integration
Add optional quality policy to EfficiencyWorkloadManifest.v2 semantics.
Bind quality evidence to exact config fingerprint.
GATE-03: missing/failed/mismatched quality blocks improvement even when candidate timing is faster.




CP2 / WP04 — Cross-lane claim gate
Refactor efficiency comparison so claim formation occurs after quality and comparability checks.
Emit QualityEfficiencyComparison.v1.
GATE-04: decision-table tests pass; existing v1 workload tests remain backward-compatible.




CP3 / WP05 — Evidence-chain and review integration
Hash/reference new artifacts; validate run/fingerprint linkage; update review.md with quality, fingerprint, baseline comparability, stability, and per-metric deltas.
GATE-05: tampering and stale-reference tests fail closed; valid run validates end to end.




CP4 / WP06 — Deterministic proving run
Use deterministic fixtures only. Demonstrate allowed improvement, quality-blocked faster candidate, incomparable config, quality-unproven candidate, and unstable measurement.
GATE-06: receipts reconstruct every outcome without live model/API dependencies.




Authorization boundary after WP06
Completion of WP06 proves ERA-EVAL-01 semantics. It does not automatically authorize later telemetry, model calls, judge use, agent execution, DataForge writes, UI work, or contract promotion.




HELD / WP07 — Rich AI inference telemetry
Adapters for TTFT, TPOT/ITL, tokens/sec, throughput, RAM, VRAM, context/output token counts, and p50/p95/p99 where sample volume justifies them.
Prerequisite: explicit authorization after GATE-06.




HELD / WP08 — Statistical and energy evidence
Warmups, sample policies, bootstrap/CI or bounded uncertainty method, energy/token or successful-task/joule where instrumentation is trustworthy.
No physical-power claim from GPU-only counters unless scope is clearly labeled.




HELD / WP09 — Judge audit
JudgeAuditArtifact.v1, AB/BA permutation, human calibration subset, family separation, disagreement preservation.
No judge as canonical truth.




HELD / WP10 — Agent efficiency
Task success + steps + tool calls + tokens + wall time + API cost/local energy; cost per successful task and joules per successful task as vectors, not automatic promotion scores.




HELD / WP11 — Execution-isolation receipt
Bind an authorized sandbox/isolation provider for agentic or untrusted workloads. ERA records policy and receipt; it does not own the sandbox.




HELD / WP12 — Durable/UI integration
DataForge Local persistence and Forge_Command review surfaces after local artifact semantics stabilize.




Merge discipline
Each work package should be independently reviewable.
No WP may silently pull a HELD scope item forward.
Any scope expansion requires an amendment or explicit operator authorization.


────────────────────────────────────────


09 — OPERATOR REVIEW PACKET


BDS-ERA-EVAL-v0.1 — 09 Operator Review Packet
Section 09 purpose: present the exact decisions required before any implementation work begins and state what each authorization does and does not permit.




Plan status
Lifecycle: proposed.
Planning is complete enough for operator review.
No repository mutation is authorized by plan creation.




Decision D1 — Admit the architecture direction
Question: Should ERA adopt configuration-pinned, quality-gated efficiency as the next evaluation architecture?
A Yes accepts the design target and non-goals.
A Yes does not authorize code changes, schema promotion, live model calls, or deployment.




Decision D2 — Authorize CP0/WP00
Question: Authorize a read-only source lock against the then-current ERA master and canonical Drive governance sources?
A Yes authorizes only bounded read operations and creation of a GATE-00 evidence/remediation packet.
A Yes does not authorize implementation changes.




Decision D3 — Local-first contract proof
Question: Keep new evaluation contracts local to ERA until the local proof demonstrates cross-repo need?
Plan recommendation: Yes.
A Yes avoids premature forge-contract-core expansion.
Promotion remains a separate authorization.




Decision D4 — First proving workload
Question: Use deterministic synthetic fixtures for ERA-EVAL-01 before any live LLM/provider/agent evaluation?
Plan recommendation: Yes.
This minimizes cost, nondeterminism, and sandbox dependency while proving semantics.




Decision D5 — Sandbox boundary
Question: Require an authorized isolation receipt before agentic, MCP-tool, external-repository, generated-code, or otherwise untrusted evaluation becomes promotion-capable?
Plan recommendation: Yes.
Trusted in-house deterministic fixtures remain allowed under the existing --trusted-target gate.




Decision D6 — Rich telemetry timing
Question: Hold TTFT/TPOT, token throughput, RAM/VRAM, energy, judge audits, and agent economics until GATE-06?
Plan recommendation: Yes.
These are valuable extensions but are not needed to prove the central governance improvement.




What an implementation authorization should name
Exact work package(s).
Source-locked ERA head.
Allowed files/directories.
Allowed contract scope.
Test/verification commands.
Whether docs are in scope.
Whether forge-contract-core changes are permitted.
Whether any live model/provider call is permitted.
Whether sandboxed execution is required.
Stop conditions.




Immediate next action if D1 and D2 are approved
Run CP0/WP00 only.
Produce GATE-00 evidence manifest with immutable head, current call graph around efficiency/quality evidence, authority table, active workload schema snapshot, current classification behavior, baseline fixture outputs, documentation parity status, and exact CP1 allowlist.
Stop if current source contradicts the plan assumptions.




Approval semantics
Approve plan only = architecture accepted; no implementation.
Approve CP0/WP00 = read-only source lock only.
Approve CP1/WP01-WP02 = local contract/fingerprint implementation only after GATE-00 pass.
Approve through WP06 = complete deterministic ERA-EVAL-01 proof; still no HELD work.
HELD work requires later explicit authorization.