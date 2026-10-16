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