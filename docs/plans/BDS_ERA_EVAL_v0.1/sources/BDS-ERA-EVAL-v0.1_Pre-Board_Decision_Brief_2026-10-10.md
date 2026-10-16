BDS-ERA-EVAL-v0.1 — Pre-Board Decision Brief — 2026-10-10
PRE-BOARD / ADVISORY / NON-AUTHORITATIVE
Evidence freshness: 2026-10-10. This brief prepares evidence for the separate BDS Board workflow. Neither this brief nor that workflow grants implementation authority; only Charlie’s explicit authorization does.


1. Review identity and exact decision at hand
The canonical compiled plan, operator packet, and Amendment 01 describe a proposed plan and later accepted rulings, while ERA implementation and Forge_Command consumption are already landed. The exact decision is how to reconcile and classify that implemented evaluation path after live read-only UI verification, without treating verification as acceptance or authorizing new ERA work.


2. Requested disposition and smallest safe authorization
Recommendation: REWORK / HOLD NEW ERA WORK, with the read-only Forge_Command evaluation projection eligible for conditional acceptance-reconciliation only. The smallest safe future decision is to source-lock ERA 0e89179b…, bind the landed work to primary authority, reconcile Amendment 01 into the canonical plan set, attach reproducible ERA tests and exact acceptance exceptions, and return. No model/provider expansion, new telemetry, judge authority, corpus change, deployment, or promotion follows.


3. Supporting evidence
ERA current main remains at 0e89179b…, three documentation commits beyond the September 30 implementation snapshot; no later ERA functional change was found. On October 9, Forge_Command PR #507 merged as 70293e65…. It live-verified the installed Evidence → Local → ERA Evaluation surface against 14 real era_evaluation_export artifacts: list/detail navigation, digest and gate display, refresh, and focus reload all worked. The page explicitly states it is read-only, does not approve or promote, and that digest verification does not make evidence true or signed. Documentation CI run 37876448991 and Forge CLI Quality Gate run 37876449037 succeeded.


4. Evidence gaps, contradictions, and confidence limits
The canonical plan still presents CP0/WP00 as the next action, while Amendment 01 says CP1–CP4 rulings occurred and many later implementation slices are landed. Amendment 01 is not reconciled into the compiled plan, index, manifest, or registry. No primary commit-by-commit authority map or final ERA acceptance receipt was found. No PR-triggered workflow is associated with ERA’s exact current head, and live UI verification proves consumption/display—not correctness, signature, production deployment binding, or acceptance of the underlying evaluation claims. Confidence is high that the read-only UI works against real stored artifacts; confidence is insufficient for full plan acceptance or new scope.


5. Important risks
Authority: implemented work may be mistaken for accepted work. Technical: stored evidence can be validly hashed yet still wrong or incomplete. Operational: inbox publishing and UI consumption add failure surfaces. Security and data: later live-model, judge, or private-corpus work would change custody and provider boundaries. Cost: richer evaluation can expand calls and operator review burden. Human factors: stale prospective records force repeated reconstruction and can conceal exceptions.


6. Unresolved questions
Which exact ERA commits and work packages did Charlie authorize and accept? Is inbox publication accepted as evidence transport only? Which current tests reproduce the 14 stored artifacts and comparison semantics? What exceptions remain for containment, baseline selection, signing, retention, provider cost, and corpus custody? Is the Forge_Command projection accepted independently of the underlying ERA implementation?


7. Plan-set and documentation impacts
AUTHORIZE/ACCEPT: record the exact accepted ERA and Forge_Command revisions, primary authority, exceptions, tests, transport boundary, and return gate; reconcile plan, amendment, manifest, registry, baseline, and ledger additively. HOLD: preserve current read-only state and prohibit new work. REWORK: build a commit-authority-test matrix and corrected packet. REJECT: record non-acceptance and separately decide preservation or rollback.


8. Scope limits, stop conditions, rollback, and return gate
No new ERA features, live model/provider calls, credentials, corpus changes, telemetry expansion, deployment, release, merge, promotion, or deletion of stored evidence. Stop on source drift, missing primary authority, failed reproducibility, changed data owner, or any non-read-only side effect. Rollback must preserve audit history. Return with frozen heads, primary authority map, reproducible ERA tests, exact UI/transport receipts, Amendment 01 reconciliation, exception ledger, and one bounded acceptance question.


9. Board disposition choices
A. REWORK / HOLD NEW ERA WORK (recommended); conditionally reconcile the read-only projection.
B. CONDITIONAL ACCEPTANCE of exact evidenced ERA/FC revisions with listed exceptions.
C. HOLD without reconciliation authority.
D. REJECT acceptance and decide preservation/rollback separately.