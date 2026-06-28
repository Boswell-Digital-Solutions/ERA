# ERA

Evidence Review & Assurance is a bounded internal-control subsystem for the Forge ecosystem.

Current slice:

```text
ERA-01A — Local Read-Only Accuracy Proof
ERA-01B — Redundancy Scan Proof
ERA-01C — Efficiency Workload Proof
ERA-02  — Unified Finding Normalization
ERA-03  — Evidence Hash Chain
ERA-04  — Differential / RTS Scaffolding
ERA-CENT-01 — ERA-to-Centipede Bundle Export
ERA-CENT-02 — Self-Healing Projection Rules
ERA-SH-01 — Self-Healing Incident Mapping Proof
```

Core doctrine:

```text
ERA finds.
ERA measures.
ERA proves.
ERA reports.
ERA does not fix.
```

## Execution Posture (read this before running)

ERA runs the target's own commands — `cargo check`, `cargo test`, `bun run test`,
`bun run build`, redundancy scanners, and manifest-declared efficiency workloads.
**That is arbitrary code execution.** "Read-only" here means only that ERA does
not modify the target's tracked git tree; it is verified after the fact by a
git-tree comparison (`read_only_invariant_scope = "target_git_tree_only"`). That
check does **not** observe writes to untracked or git-ignored paths, writes
outside the repository, network activity, or environment changes, and ERA has no
execution sandbox yet.

Because of this, ERA fails closed: `era run` refuses to execute unless you
explicitly attest that the target is trusted with `--trusted-target`. Only run
trusted, in-house repositories until a real execution sandbox lands.

```bash
python -m era_cli run --repo /path/to/trusted/repo --lanes accuracy --mode full --trusted-target
```

Each run records an `execution_posture` block (`executes_target_code`, `sandbox`,
`target_trust`, `attested_by`) in `run.json` so the receipt reflects how the run
was authorized.

## Usage

Run from the `ERA/` directory:

```bash
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode full --trusted-target
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy --mode changed-files --baseline main --trusted-target
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes redundancy --mode full --trusted-target
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes efficiency --mode full --trusted-target
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy,redundancy --mode full --trusted-target
python -m era_cli run --repo /home/charlie/Forge/ecosystem/Forge_Command --lanes accuracy,redundancy,efficiency --mode full --trusted-target
python -m era_cli report --latest
python -m era_cli validate --latest
```

`--trusted-target` is required for every `run`; without it ERA fails closed and
runs nothing. See **Execution Posture** below.

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

## Efficiency Workloads

Efficiency workloads are declared in:

```text
ERA/config/workload_manifests/<repo_name>.json
```

ERA-01C only makes efficiency regression or improvement claims when:

```text
a workload manifest exists
the workload ran successfully
timing variance is not unstable
a baseline efficiency artifact exists
```

Workload admission is bounded:

```text
cwd_subpath must resolve inside the target repository (escapes are skipped, not run)
the workload executable must be on the effective allowlist
manifest provenance (manifest_sha256) is recorded in the run evidence
```

The effective allowlist is a conservative built-in set plus any executables an
operator declares in:

```text
ERA/config/efficiency_workload_allowlist.json
```

Workloads outside the allowlist, or with an escaping `cwd_subpath`, are admitted
as `skipped` with a reason and are never executed.

## Unified Finding Model

ERA-02 standardizes the internal evidence chain as:

```text
ToolRawArtifact.v1
ToolNormalizedResult.v1
LaneFindingDraft.v1
ERAFinding.v1
ERAScore.v1
```

Tool parsers only emit `ToolNormalizedResult.v1`. Promotion into lane drafts, final findings, and scores happens in the shared contract layer so risk, confidence, raw evidence references, and lane-specific details stay aligned across all lanes.

## Evidence Hash Chain

ERA-03 writes `hashes.json` with both file hashes and a structural `ERAEvidenceHashChain.v1` section:

```text
raw artifacts
normalized results
lane finding drafts
ERA findings
ERA scores
review artifact
```

`validate --latest` recomputes file hashes, embedded object hashes, review hash references, and finding-to-raw-evidence references.

## Differential / RTS Scaffolding

Changed-files accuracy runs emit `TestSelectionArtifact.v1` with:

```text
baseline and current commit
changed files and file classifications
candidate and selected tests
RTS level cap
selection safety class
full-gate fallback rationale
```

ERA-04 records Level 1 changed-file metadata and an advisory Level 2 path for directly changed test files. It still falls back to full configured accuracy gates unless a future targeted runner can prove a safer selective execution path.

## Centipede Export

Every ERA run writes:

```text
ERA/artifacts/era-runs/<run_id>/centipede_bundle.json
```

ERA-CENT-01 emits a `centipede.intake.v1` bundle with a Centipede run record, lane admissions, decision traces, and evidence bundles mapped from ERA findings.

ERA-CENT-02 adds conservative Self-Healing projections. ERA emits `centipede.self_healing_projection.v1` only for actionable findings with raw evidence, known affected scope, supporting lane refs, and supporting trace refs. Blocked findings, missing-evidence findings, informational findings, and intentional exceptions remain evidence-only. Every projection requires operator review; proposal generation is required only when a bounded remediation path is plausible. Registry projection arrays remain empty until registry-specific rules exist.

## Self-Healing Feed

ERA-SH-01 proves the governed feed path:

```text
ERA centipede_bundle.json
ForgeCommand Centipede import
Centipede self_healing projection outbox
Self-Healing projection intake
Self-Healing incident queue
DoppelCore intake receipt
```

ForgeCommand returns the projection receipt, mapped incident, raw evidence digest, normalized digest, and DoppelCore intake receipt when an ERA projection is consumed.
