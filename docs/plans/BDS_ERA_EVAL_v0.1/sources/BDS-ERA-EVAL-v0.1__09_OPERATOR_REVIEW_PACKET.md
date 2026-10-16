BDS-ERA-EVAL-v0.1 — 09 Operator Review Packet
Section 09 purpose: present the exact decisions required before any implementation work begins and state what each authorization does and does not permit.


Plan status
Lifecycle: proposed.
Planning is complete enough for operator review.
No repository mutation is authorized by plan creation.


Decision D1 — Admit the architecture direction
Question: Should ERA adopt configuration-pinned, quality-gated efficiency as the next evaluation architecture?
A Yes accepts the design target and non-goals.
A Yes does not authorize code changes, schema promotion, live model calls, or deployment.


Decision D2 — Authorize CP0/WP00
Question: Authorize a read-only source lock against the then-current ERA master and canonical Drive governance sources?
A Yes authorizes only bounded read operations and creation of a GATE-00 evidence/remediation packet.
A Yes does not authorize implementation changes.


Decision D3 — Local-first contract proof
Question: Keep new evaluation contracts local to ERA until the local proof demonstrates cross-repo need?
Plan recommendation: Yes.
A Yes avoids premature forge-contract-core expansion.
Promotion remains a separate authorization.


Decision D4 — First proving workload
Question: Use deterministic synthetic fixtures for ERA-EVAL-01 before any live LLM/provider/agent evaluation?
Plan recommendation: Yes.
This minimizes cost, nondeterminism, and sandbox dependency while proving semantics.


Decision D5 — Sandbox boundary
Question: Require an authorized isolation receipt before agentic, MCP-tool, external-repository, generated-code, or otherwise untrusted evaluation becomes promotion-capable?
Plan recommendation: Yes.
Trusted in-house deterministic fixtures remain allowed under the existing --trusted-target gate.


Decision D6 — Rich telemetry timing
Question: Hold TTFT/TPOT, token throughput, RAM/VRAM, energy, judge audits, and agent economics until GATE-06?
Plan recommendation: Yes.
These are valuable extensions but are not needed to prove the central governance improvement.


What an implementation authorization should name
Exact work package(s).
Source-locked ERA head.
Allowed files/directories.
Allowed contract scope.
Test/verification commands.
Whether docs are in scope.
Whether forge-contract-core changes are permitted.
Whether any live model/provider call is permitted.
Whether sandboxed execution is required.
Stop conditions.


Immediate next action if D1 and D2 are approved
Run CP0/WP00 only.
Produce GATE-00 evidence manifest with immutable head, current call graph around efficiency/quality evidence, authority table, active workload schema snapshot, current classification behavior, baseline fixture outputs, documentation parity status, and exact CP1 allowlist.
Stop if current source contradicts the plan assumptions.


Approval semantics
Approve plan only = architecture accepted; no implementation.
Approve CP0/WP00 = read-only source lock only.
Approve CP1/WP01-WP02 = local contract/fingerprint implementation only after GATE-00 pass.
Approve through WP06 = complete deterministic ERA-EVAL-01 proof; still no HELD work.
HELD work requires later explicit authorization.