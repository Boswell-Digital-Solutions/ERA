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