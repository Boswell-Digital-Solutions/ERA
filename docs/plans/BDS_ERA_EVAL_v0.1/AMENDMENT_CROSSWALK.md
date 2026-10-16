# ERA evaluation — amendment and evidence crosswalk

This is the current reading guide for the imported historical proposal. It does not replace the existing implementation records or accept an unclosed gate.

| Historical source statement | Reconciled reading | Owning evidence |
|---|---|---|
| Section 02: no sandbox / external sandbox owner | ERA contains the authorized sandbox provider, with the disclosed non-jail limitation; actual posture comes from each receipt | [Amendment 01](../../eval/BDS-ERA-EVAL-v0.1_AMENDMENT_01.md), current `doc/system/03-runtime-boundary.md` |
| Sections 04/06: incomplete claim vocabulary | Include `no_baseline` and `no_claim_unstable`; unstable efficiency and unstable-claim status correspond | Amendment 01 A1; `era_core/eval_contracts.py` |
| Section 05: baseline and quality selection | Validate prior evidence, compare fingerprints, then require qualified quality; retain rejection reasons | Amendment 01 A2; committed proving receipt |
| N19: require trusted-target unconditionally | Refuse when neither containment nor explicit trusted attestation exists | Amendment 01 A4; current README execution posture |
| WP06 remains future work | Committed GATE-06 records seven passing expected scenarios; this intake does not repeat them | [GATE-06 evidence](../../eval/BDS-ERA-EVAL-v0.1_GATE-06_proving_run.md), adjacent JSON receipt |
| WP11: receipt from externally owned sandbox | ERA records its authorized provider and requires posture comparison dimensions for opted-in workloads | Amendment 01 A3/A8; current contract-surface docs |
| WP12: local_to_era export pending contract decision | The same interface record's later update records admission through RFC-ERA-EVAL-01 and later consumer decisions; use the admitted shape | [WP12 interface and dated updates](../../eval/BDS-ERA-EVAL-v0.1_WP12_INTERFACE.md), current `doc/system/02-contract-surface.md` |

The Drive Amendment 01 is preserved as a native-Doc snapshot. The pre-existing repository Amendment 01 remains in place. The current compilation rule is: read original components 00–09 together with Amendment 01, this crosswalk and the dated owning-repo evidence; never read the historical compiled proposal alone as present-tense system truth. This intake does not silently regenerate the historical compiled copy or claim byte parity between native Docs and raw exports.
