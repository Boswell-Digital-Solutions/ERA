        # ERA - Compiled System Reference

        **Designation:** ERA
        **Document role:** Canonical compiled technical reference for Evidence Review and Assurance
        **Source:** `doc/system/`
        **Build command:** `bash doc/system/BUILD.sh`
        **Document version:** 2.0 (2026-06-22) - canonical compliance migration
        **Protocol:** BDS Documentation Protocol v2.0; BDS Repo Documentation System Canonical Compliance Standard

        > **Generated artifact warning:** `doc/ERASYSTEM.md` is assembled output. Edit
        > the source modules under `doc/system/` and rebuild. Hand edits to the
        > compiled artifact are overwritten by the next build.

        Assembly contract:

        - Command: `bash doc/system/BUILD.sh`
        - Validation: `bash doc/system/validate_snapshots.sh` runs during assembly
        - Primary output: `doc/ERASYSTEM.md`

        This `doc/system/` tree is the canonical source of truth for ERA. It uses
        explicit **truth classes**: canonical facts define repo role, authority
        boundaries, contract behavior, runtime behavior, and verification doctrine;
        snapshot facts are dated, audit-derived counts and current implementation
        inventory that may drift between audits.

        | Part | File | Contents |
        | --- | --- | --- |
        | §1 | `00_overview/01-overview.md` | 01 Overview |
| §2 | `10_service-contract/02-contract-surface.md` | 02 Contract Surface |
| §3 | `20_runtime/03-runtime-boundary.md` | 03 Runtime Boundary |
| §4 | `30_dependencies/04-dependencies.md` | 04 Dependencies |
| §5 | `40_governance/05-governance.md` | 05 Governance |
| §6 | `50_operations/06-verification.md` | 06 Verification |
| §7 | `99_appendices/90-appendices.md` | 90 Appendices |

        ## Quick Assembly

        ```bash
        bash doc/system/BUILD.sh
        ```
