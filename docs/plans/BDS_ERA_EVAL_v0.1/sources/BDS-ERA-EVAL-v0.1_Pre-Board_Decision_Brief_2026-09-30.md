BDS-ERA-EVAL-v0.1 — Pre-Board Decision Brief — 2026-09-30
PRE-BOARD / ADVISORY / NON-AUTHORITATIVE
Only Charlie’s explicit authorization grants implementation authority; neither this brief nor the Board workflow does.


1. Review identity and exact decision at hand
ERA packet requests D1–D6 rulings and CP0/WP00 only. Decide how to classify and reconcile implementation that advanced far beyond that prospective request.


2. Current requested disposition and smallest safe authorization
REWORK / HOLD ALL NEW WORK. Smallest safe option after Board review: evidence-only reconciliation at exact head 2d8b1746583bb1db4fe7c1bf400613e51d2ec700; no new code or live use.


3. Supporting evidence
Drive source-locks 13180a8837590476e3c8ff6f115f8a3c571b768d; GitHub is 37 commits ahead at 2d8b1746583bb1db4fe7c1bf400613e51d2ec700. The delta adds evaluation contracts, quality/comparability gates, telemetry, judge/agent isolation, snapshots, export, and DataForge Local inbox publishing. PR bodies report local tests; no exact-head combined status or PR-triggered workflow was found.
Packet: https://docs.google.com/document/d/18U8ipS8SMNLlcb8taosS6yKQknhCf8hDdQc3yO97904/edit
Comparison: https://github.com/Boswell-Digital-Solutions/ERA/compare/13180a8837590476e3c8ff6f115f8a3c571b768d...2d8b1746583bb1db4fe7c1bf400613e51d2ec700


4. Evidence gaps, contradictions, and confidence limits
Prospective Drive authority conflicts with implemented source. Primary authorization for the delta, current baseline, exact-head CI, and acceptance evidence are unavailable.


5. Important risks
Authority by momentum; unreviewed evaluation/publishing paths; telemetry and judge data boundaries; provider cost; single-operator reconciliation burden.


6. Unresolved questions
Which commits were authorized and accepted; whether inbox publication is evidence-only; applicable provider, retention, and cost limits; exact closure tests.


7. Plan-set and documentation impacts
AUTHORIZE: revise plan, manifest, registry, packet, baseline, ledger, and receipt to the accepted SHA. HOLD: record freeze/prohibitions. REWORK: add commit-authority matrix and current evidence. REJECT: record non-acceptance and separate rollback/preservation direction.


8. Scope limits, prohibitions, stop conditions, rollback needs, and return gate
No new features, calls, credentials, deployment, release, merge, or acceptance. Stop on drift, network activity, spend, or missing data authority. Preserve history. Return with frozen SHA, primary authority map, reproducible tests/CI, and revised records.


9. Concrete disposition choices
A. REWORK / HOLD ALL NEW WORK — recommended. B. Conditional reconciliation-only. C. Reject acceptance and decide preservation/rollback. D. Accept only exact, evidenced scope and SHA.


Evidence fresh through September 30, 2026.