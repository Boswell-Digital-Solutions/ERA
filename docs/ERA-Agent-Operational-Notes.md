# ERA Agent Notes

ERA is read-only with respect to the evaluated repository.

Hard rules for this slice:

```text
No patches.
No dependency installation.
No formatters in write mode.
No git add/commit/checkout/reset/stash/clean.
No hiding failed, skipped, or blocked commands.
```

Allowed evaluation behavior in ERA-01A:

```text
Capture target metadata.
Run configured accuracy commands.
Write evidence only inside ERA/artifacts/.
Report failures as evidence.
```

Allowed evaluation behavior in ERA-01B:

```text
Run configured redundancy commands.
Record missing redundancy tools as blocked gates.
Honor operator-approved intentional redundancy exceptions.
Keep redundancy findings as review candidates, not defects.
```

Allowed evaluation behavior in ERA-01C:

```text
Load manifest-defined efficiency workloads.
Run repeated timing measurements with the internal timer.
Record variance classifications and baseline comparisons.
Avoid regression or improvement claims when baseline evidence is absent.
```

Allowed evaluation behavior in ERA-02:

```text
Promote raw evidence through shared normalized-result, draft, finding, and score contracts.
Preserve lane-specific details without letting parsers emit ERAFinding.v1 directly.
Keep risk and confidence as separate dimensions in all promoted findings.
Fail validation when draft, finding, or score references are malformed.
```

Allowed evaluation behavior in ERA-03:

```text
Write hashes.json with file hashes and a structural evidence hash chain.
Record raw, normalized, draft, finding, score, and review artifact hash references.
Fail validation on stale object hashes, stale review hashes, or broken raw evidence references.
Require clear_issue findings to include raw evidence refs and hashes.
```

Allowed evaluation behavior in ERA-04:

```text
Capture changed-file metadata for changed-files accuracy runs.
Classify changed files and record the RTS level cap.
Record directly changed test files as advisory selected tests only.
Fall back to full configured accuracy gates unless selection safety supports narrower proof.
```

Allowed evaluation behavior in ERA-CENT-01:

```text
Export ERA evidence into centipede.intake.v1 bundle shape.
Map ERA runs, lane admissions, decision traces, and evidence bundles.
Fail ERA validation when centipede_bundle.json has broken run bindings.
```

Allowed evaluation behavior in ERA-CENT-02:

```text
Emit Self-Healing projections only for actionable evidence-backed findings.
Keep blocked, informational, intentional-exception, and evidence-missing findings evidence-only.
Require operator_review_required=true on every projection.
Set proposal_required only when bounded remediation is plausible.
Include evidence bundle, supporting lane, and supporting trace references on every projection.
Keep registry projection arrays empty until registry-specific rules exist.
```

Allowed integration behavior in ERA-SH-01:

```text
Feed ERA-originated Self-Healing projections only through Centipede intake.
Require Self-Healing incidents to retain raw_evidence_sha256 and normalized_digest_sha256.
Require projection receipts when projections are consumed or blocked.
Require DoppelCore intake receipts when a projection maps to a Self-Healing incident.
Keep operator review mandatory; no repair action is executed by ERA or the feed proof.
```

Operator notes:

```text
Target repo failures are evidence, not ERA crashes.
Missing tools become blocked gates, not false code failures.
```
