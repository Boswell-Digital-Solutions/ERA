# BDS-ERA-EVAL-v0.1 — Amendment 01 (draft for operator placement)

Date: 2026-09-30
Status: draft. The operator placed a copy in `/Forge/Plans/BDS-ERA-EVAL-v0.1`. The plan set index and compiled plan are not yet updated.
Basis: operator rulings of 2026-09-30 during implementation of CP1 to CP4.

## A1. claim_status vocabulary (sections 04 and 06)

The vocabulary is:

```text
permitted, quality_blocked, quality_unproven, no_baseline,
incomparable, no_claim_unstable, evidence_blocked
```

- `no_baseline`: nothing eligible exists to compare against. Section 05 already lists it. Sections 04 and 06 omitted it.
- `no_claim_unstable`: the timing is too unstable for a claim. It is not broken evidence and it is not a configuration mismatch.

A comparison with `efficiency_status: unstable` must have `claim_status: no_claim_unstable`, and the reverse.

## A2. Baseline eligibility (section 05)

An ERA-EVAL-01 baseline is eligible only when all of these hold:

1. Its evidence validates.
2. Its fingerprint matches the required comparison dimensions.
3. Its quality gate passed.

ERA checks them in that order. ERA keeps every rejected run in `baseline_rejections` with one reason: `evidence_invalid`, `fingerprint_incomparable`, `quality_failed`, or `quality_unproven`.

If comparable prior runs exist and all fail qualification, the claim is `no_baseline`. No separate `no_qualified_baseline` state exists. If prior runs exist and none is comparable, the claim is `incomparable`. If only unusable evidence remains, the claim is `evidence_blocked`.

Test cases N21 and N22 cover this rule.

## A3. Execution isolation (section 02, AUTHORITY_GAP-02, decision D5)

PR #5 added a contained execution backend in `era_core/sandbox.py` (no network, overlay-protected target). Section 02 said ERA has no sandbox. That statement was out of date.

**Operator ruling 2 (2026-09-30): yes.** `era_core/sandbox.py` is the authorized isolation provider for decision D5. AUTHORITY_GAP-02 is closed for that provider.

Limits that stay in force:

- A contained run is not a full jail. It can still read other host paths.
- A run counts as isolated only when its receipt says `sandbox: contained`. A run with `sandbox: none` is a trusted-target run.
- Section 02 said "ERA does not own the sandbox". That sentence is replaced: the sandbox lives in ERA, and ERA records the receipt for it (WP11).

## A4. Trust gate wording (section 07, case N19)

`--trusted-target` is now needed only when no containment is available or containment is off. Case N19 reads: a run refuses before execution when there is neither containment nor an attestation.

## A5. Contract fields added during implementation

- `EvaluationConfigFingerprint.v1`: `subject_identity` and `config_digest`. The digest excludes run ID, time, and commit SHA.
- `QualityEfficiencyComparison.v1`: `baseline_rejections`.
- Execution identity includes the sandbox posture: `sandbox`, `sandbox_backend`, `network`, `target_filesystem`.

## A6. Quality results source (section 05)

ERA reads quality results from a file that already exists in the target tree. A contained run discards writes to the target, so a workload command cannot create the file. A missing file gives `quality_unproven`. Live-model work needs a different route (a later work package).

## A7. Open item outside this plan

The legacy v1 baseline selection in `era_core/efficiency.py` orders prior runs by `completed_at` at one-second resolution and has the same tie risk that WP06 fixed for fingerprints. No plan covers it.

## A8. Isolation gating (WP11, decision D5)

A workload requires isolation when its `subject_kind` is `agent` or it declares an agentic, MCP-tool, generated-code, external-repo, or untrusted trait. An unsatisfied `IsolationReceipt.v1` maps to `evidence_blocked`, with the reason in `blocked_reasons`. No claim status was added for it. The operator can rule to add a dedicated `isolation_required` claim status later.

Ruling 3 (sandbox posture in the execution identity) was recorded in the fingerprint, but comparison did not require it. WP11 makes `execution.sandbox`, `execution.network`, and `execution.target_filesystem` required comparison dimensions for every opted-in workload.
