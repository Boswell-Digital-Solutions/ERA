BDS-ERA-EVAL-v0.1 — 07 QA and Verification Plan
Section 07 purpose: prove the new evaluation semantics fail closed, remain reproducible, and preserve ERA's evidence chain.


Verification layers
Contract validation.
Fingerprint determinism.
Quality-gate correctness.
Baseline-comparability correctness.
Metric/stability correctness.
Cross-artifact hash integrity.
Review rendering.
Backward compatibility for legacy EfficiencyWorkloadManifest.v1.
Read-only-to-target invariant.
Trusted-target execution gate.


Required positive regression cases
P01 same config + quality pass + stable faster candidate => improvement, permitted.
P02 same config + quality pass + stable slower candidate => regression, permitted.
P03 same config + quality pass + delta inside threshold => within_range, permitted.
P04 legacy v1 generic command workload continues current behavior when no quality policy is declared.
P05 repeated construction of an identical normalized config produces the same fingerprint hash.


Required negative regression cases
N01 faster candidate + quality failed => quality_blocked; no improvement claim.
N02 faster candidate + quality missing => quality_unproven.
N03 model/subject revision changes on a required dimension => incomparable.
N04 quantization changes on a required dimension => incomparable.
N05 prompt/template hash changes on a required dimension => incomparable.
N06 dataset/fixture hash changes => incomparable.
N07 scorer or harness version changes when declared binding => incomparable.
N08 hardware fingerprint changes for hardware-bound timing => incomparable.
N09 concurrency or batch changes for a sensitive metric => incomparable.
N10 candidate or baseline variance unstable => unstable; no improvement/regression claim.
N11 quality artifact references a different config fingerprint => evidence_blocked.
N12 metric vector references a different config fingerprint => evidence_blocked.
N13 tampered quality artifact hash => validate fails.
N14 tampered fingerprint object or stale digest => validate fails.
N15 baseline artifact exists but does not satisfy comparison dimensions => no comparable baseline.
N16 missing metric direction => evidence_blocked or no claim.
N17 unknown required comparison field => no claim.
N18 candidate command fails/times out => existing blocked/failure behavior remains controlling.
N19 untrusted target without explicit attestation => run refuses before execution and writes no false proof.
N20 read-only invariant failure/head change during run => no quality-efficiency claim.


Review artifact assertions
review.md must show candidate fingerprint ID.
review.md must show quality gate status.
review.md must show baseline run/fingerprint.
review.md must show comparability status and blocked reason.
review.md must show stability/uncertainty state.
review.md must show metric deltas separately.
review.md must never render 'improvement' without the gating context above.


Hash-chain assertions
New evaluation artifacts must be embedded or referenced in hashes.json/evidence chain using existing ERA conventions.
Validation must reject stale references, missing artifacts, mismatched run IDs, mismatched config hashes, and broken raw-evidence references.


Source-lock verification
GATE-00 records immutable ERA head, relevant file blob hashes, current tests, current manifest behavior, and current doc/plan authority. Tests are written against the locked baseline, not memory of the codebase.


First live proof gate
No live model/provider/agent run is required to close ERA-EVAL-01. After deterministic proof closes, a separate operator decision may authorize one local model/config pair to demonstrate a real quality-plus-latency comparison.