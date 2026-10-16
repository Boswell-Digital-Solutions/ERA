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