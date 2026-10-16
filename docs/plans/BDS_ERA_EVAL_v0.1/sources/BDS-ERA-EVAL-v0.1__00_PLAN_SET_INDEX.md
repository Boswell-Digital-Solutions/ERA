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