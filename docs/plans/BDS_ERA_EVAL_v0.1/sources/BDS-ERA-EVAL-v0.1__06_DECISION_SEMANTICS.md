BDS-ERA-EVAL-v0.1 — 06 Decision Semantics
Section 06 purpose: define how ERA labels evidence so operators and downstream systems cannot mistake speed, quality, or comparability for authorization.


Evidence states
quality_status: passed | failed | unproven | invalid.
comparability_status: comparable | incomparable | unknown.
efficiency_status: improvement | regression | within_range | unstable | not_evaluated.
claim_status: permitted | quality_blocked | quality_unproven | incomparable | evidence_blocked.


Meaning of 'improvement'
ERA may use the word improvement for a declared efficiency metric only when:
the candidate quality gate passed;
the quality and efficiency artifacts reference the same candidate fingerprint;
the baseline is comparable under all required dimensions;
both candidate and baseline evidence validate;
the measurement is stable under the active policy;
the metric direction is declared;
the delta crosses the manifest's improvement threshold.


Meaning of 'regression'
A regression is a comparable, evidence-backed worsening beyond the declared threshold. A quality failure is not reduced to an efficiency regression; it is quality_blocked and should remain visible as the controlling failure.


Meaning of 'incomparable'
Incomparable is a truthful outcome, not a system error. It means the evidence cannot support a fair baseline claim under the active comparison policy. ERA may still display the raw measurements side by side with a clear no-comparison label.


Meaning of 'quality_unproven'
No quality artifact, missing hard-floor result, mismatched fingerprint, or incomplete quality evidence prevents an efficiency improvement claim. 'No evidence of quality regression' must never be rewritten as 'quality passed.'


Existing ERA classifications
Existing lane classification values remain available for current workloads. ERA-EVAL-01 should add the smallest compatible classification surface needed for quality_blocked, quality_unproven, and incomparable behavior without breaking legacy generic timing workloads.


ERAScore rule
ERAScore.v1 remains a summary of classifications and evidence counts. It must not become a weighted aggregate that can offset a failed quality, security, authority, or evidence-integrity gate.


Operator decisions
ERA does not make accept/reject product decisions. It produces evidence classifications and review candidates. Forge_Command/operator actions remain outside ERA's own authority.


Downstream projection
A comparable efficiency regression with valid quality evidence may continue to qualify for the existing efficiency-regression review projection.
A quality failure may qualify for a separate future projection only after a bounded finding type and downstream mapping are explicitly authorized.
Incomparable, quality_unproven, unstable, or evidence_blocked states are evidence-only by default and must not trigger automatic remediation proposals.


Unknown state rule
Unknown required policy, missing required field, unrecognized comparison dimension, or unsupported metric direction fails closed to no claim.