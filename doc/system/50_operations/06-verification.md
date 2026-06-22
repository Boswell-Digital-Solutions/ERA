            # Verification

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            Common operator commands are:

```bash
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode full
python -m era_cli report --latest
python -m era_cli validate --latest
```

Unit tests live under `tests/` and should be run before changing artifact or contract behavior.
