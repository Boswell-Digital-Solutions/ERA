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