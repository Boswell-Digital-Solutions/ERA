            # Verification

            **Document version:** 2.0 (2026-06-22) - canonical compliance migration

            Common operator commands are:

```bash
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode full
python -m era_cli report --latest
python -m era_cli validate --latest
```

Unit tests live under `tests/` and should be run before changing artifact or contract behavior.

## Evaluation Proving Run (BDS-ERA-EVAL-v0.1 GATE-06)

Run `python3 scripts/eval_proving_run.py` to prove the quality-gated claim semantics. The script runs seven scenarios through the real run path with local sleep commands. It calls no model, provider, agent, or network. It checks that each scenario reaches its expected claim, that the run validates, and that `era_core/eval_reconstruct.py` rebuilds the same claim from the artifacts on disk. Details and the committed receipt are in `docs/eval/BDS-ERA-EVAL-v0.1_GATE-06_proving_run.md`.
