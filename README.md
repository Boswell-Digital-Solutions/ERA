# ERA

Evidence Review & Assurance is a bounded internal-control subsystem for the Forge ecosystem.

Current slice:

```text
ERA-01A — Local Read-Only Accuracy Proof
ERA-01B — Redundancy Scan Proof
```

Core doctrine:

```text
ERA finds.
ERA measures.
ERA proves.
ERA reports.
ERA does not fix.
```

## Usage

Run from the `ERA/` directory:

```bash
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode full
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode changed-files --baseline main
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes redundancy --mode full
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy,redundancy --mode full
python -m era_cli report --latest
python -m era_cli validate --latest
```

Artifacts are written under:

```text
ERA/artifacts/era-runs/<run_id>/
```

ERA never writes inside the evaluated target repository.

## Redundancy Exceptions

Optional operator-approved redundancy exceptions live at:

```text
ERA/config/intentional_redundancy_exceptions.json
```

Each entry should use the local `IntentionalRedundancyException.v1` shape and is treated as review context, not as a parser instruction to delete evidence.
