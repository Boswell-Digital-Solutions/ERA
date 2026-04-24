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

Operator notes:

```text
Target repo failures are evidence, not ERA crashes.
Missing tools become blocked gates, not false code failures.
```
