plan_id: "BDS-ERA-EVAL-v0.1"
title: "ERA Quality-Gated Evaluation Expansion"
version: "0.1"
lifecycle: "proposed"
authority: "Plan candidate only; no repository mutation. CP0/WP00 requires separate explicit authorization."
decision_owner: "Charlie Boswell, Sole BDS Operator"
prepared: "Sep 30, 2026"
timezone: "America/Chicago"
parent_extension_target:
  - "ERA-01C"
  - "ERA-02"
  - "ERA-03"
related_plans:
  - "BDS-GRI-01"
proposed_canonical_owner: "Boswell-Digital-Solutions/ERA"
source_lock_required: true
primary_candidate_consumer:
  - "Boswell-Digital-Solutions/ERA"
  - "Forge_Command (later review consumer)"
  - "DataForge Local (later durable evidence consumer)"
canonical_drive_destination: "/Forge/Plans/BDS-ERA-EVAL-v0.1"
compilation: "00-09 -> BDS-ERA-EVAL-v0.1_COMPILED_PLAN_SET.md"
rulings:
  - "Quality must pass on the exact pinned configuration before ERA may claim efficiency improvement."
  - "Required baseline-comparison dimensions must match or the result is incomparable."
  - "ERA reports metric vectors; ERAScore.v1 must not become a weighted universal optimization score."
  - "Missing or invalid quality evidence blocks improvement claims."
  - "ERA retains no mutation, promotion, routing, or operator authority."
authority_gaps:
  - id: "AUTHORITY_GAP-01"
    state: "open_by_design"
    subject: "shared contract promotion"
  - id: "AUTHORITY_GAP-02"
    state: "open_for_agentic_or_untrusted"
    subject: "execution isolation provider"
  - id: "AUTHORITY_GAP-03"
    state: "open"
    subject: "private/rotating evaluation corpus custody"
  - id: "AUTHORITY_GAP-04"
    state: "open"
    subject: "cross-hardware normalization"
  - id: "AUTHORITY_GAP-05"
    state: "held"
    subject: "LLM judge calibration authority"
work_packages:
  - { id: "WP00", checkpoint: "CP0", state: "proposed", gate: "GATE-00", purpose: "read-only source lock" }
  - { id: "WP01", checkpoint: "CP1", state: "held_until_gate_00", gate: "GATE-01", purpose: "local contract proof" }
  - { id: "WP02", checkpoint: "CP1", state: "held_until_gate_01", gate: "GATE-02", purpose: "fingerprint and comparability engine" }
  - { id: "WP03", checkpoint: "CP2", state: "held_until_gate_02", gate: "GATE-03", purpose: "quality-gate integration" }
  - { id: "WP04", checkpoint: "CP2", state: "held_until_gate_03", gate: "GATE-04", purpose: "cross-lane claim gate" }
  - { id: "WP05", checkpoint: "CP3", state: "held_until_gate_04", gate: "GATE-05", purpose: "evidence-chain and review integration" }
  - { id: "WP06", checkpoint: "CP4", state: "held_until_gate_05", gate: "GATE-06", purpose: "deterministic proving run" }
  - { id: "WP07", checkpoint: "HELD", state: "held", purpose: "rich AI inference telemetry" }
  - { id: "WP08", checkpoint: "HELD", state: "held", purpose: "statistical and energy evidence" }
  - { id: "WP09", checkpoint: "HELD", state: "held", purpose: "judge audit" }
  - { id: "WP10", checkpoint: "HELD", state: "held", purpose: "agent efficiency" }
  - { id: "WP11", checkpoint: "HELD", state: "held", purpose: "execution-isolation receipt" }
  - { id: "WP12", checkpoint: "HELD", state: "held", purpose: "durable/UI integration" }
gates:
  - "GATE-00: source/authority lock"
  - "GATE-01: local contracts validate"
  - "GATE-02: comparability mismatches fail closed"
  - "GATE-03: quality failure/missing evidence blocks improvement"
  - "GATE-04: decision-table and backward-compatibility proof"
  - "GATE-05: evidence/hash/review integration proof"
  - "GATE-06: deterministic end-to-end proving run"
house_form_conformance: "BDS-PSS-001"