"""Load and render quality-gated evaluation evidence for review.md (WP05)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVAL_KINDS = ("fingerprint", "quality_gate", "metric_vector", "comparison")


def load_eval_artifacts(run_root: Path, refs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``workload_id -> {kind: payload}`` for refs that exist. A bad file is skipped."""
    loaded: dict[str, dict[str, Any]] = {}
    for workload_id, entry in (refs or {}).items():
        artifacts: dict[str, Any] = {}
        for kind in EVAL_KINDS:
            ref = entry.get(kind)
            if not ref:
                continue
            try:
                artifacts[kind] = json.loads((run_root / ref["path"]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        loaded[workload_id] = artifacts
    return loaded


def eval_hash_values(refs: dict[str, Any]) -> list[str]:
    return [entry[kind]["sha256"] for entry in (refs or {}).values() for kind in EVAL_KINDS if entry.get(kind)]


def _fmt(value: Any) -> str:
    return "n/a" if value is None else str(value)


def render_eval_section(refs: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> list[str]:
    """Render the gating context for every v2 workload.

    Every workload shows its quality status, fingerprint, baseline, comparability,
    stability, and per-metric deltas. The word `improvement` appears only for a
    permitted claim, next to the facts that allow it.
    """
    if not refs:
        return []
    lines = ["", "### Quality-Gated Evaluation"]
    for workload_id in sorted(refs):
        entry, found = refs[workload_id], artifacts.get(workload_id, {})
        fingerprint, gate = found.get("fingerprint"), found.get("quality_gate")
        vector, comparison = found.get("metric_vector"), found.get("comparison")
        lines.extend(["", f"#### {workload_id}"])
        if comparison is None:
            lines.append("- claim status: `evidence_blocked` (no comparison artifact)")
        else:
            lines.append(f"- claim status: `{comparison['claim_status']}`")
        lines.append(f"- quality gate status: `{_fmt((gate or {}).get('gate_status') or entry.get('quality_status'))}`")
        for reason in (gate or {}).get("failure_reasons", []) or []:
            lines.append(f"  - quality reason: {reason}")
        lines.append(f"- candidate fingerprint: `{_fmt((fingerprint or {}).get('fingerprint_id'))}`")
        lines.append(f"- candidate config digest: `{_fmt((fingerprint or {}).get('config_digest'))}`")
        if comparison is not None:
            lines.append(f"- baseline run: `{_fmt(comparison.get('baseline_run_id'))}`")
            lines.append(f"- baseline fingerprint: `{_fmt(comparison.get('baseline_fingerprint_id'))}`")
            lines.append(f"- comparability: `{comparison['comparability_status']}`")
            for reason in comparison.get("blocked_reasons", []):
                lines.append(f"  - blocked reason: {reason}")
        for problem in entry.get("problems", []):
            lines.append(f"  - evidence problem: {problem}")
        uncertainty = (vector or {}).get("variance_or_uncertainty") or {}
        deltas = (comparison or {}).get("metric_deltas") or {}
        baseline_stability = next((d.get("baseline_stability") for d in deltas.values()), None)
        lines.append(
            f"- stability: candidate `{_fmt(uncertainty.get('variance_classification'))}`,"
            f" baseline `{_fmt(baseline_stability)}`"
        )
        lines.extend(["", "| metric | direction | candidate | baseline | delta | delta % |", "|---|---|---:|---:|---:|---:|"])
        if deltas:
            for name, delta in sorted(deltas.items()):
                lines.append(
                    f"| {name} | {delta['direction']} | {delta['candidate']} | {delta['baseline']} |"
                    f" {delta['delta']} | {delta['delta_pct']} |"
                )
        else:
            lines.append("| none | n/a | n/a | n/a | n/a | n/a |")
        if comparison is not None and comparison["claim_status"] == "permitted":
            lines.append(
                f"- efficiency outcome: `{comparison['efficiency_status']}`, reported because quality passed,"
                " the baseline is comparable, and the timing is stable"
            )
        else:
            lines.append("- efficiency outcome: no improvement or regression claim was made")
        rejections = (comparison or {}).get("baseline_rejections") or []
        if rejections:
            lines.append("- rejected baselines:")
            for item in rejections:
                lines.append(f"  - `{item['run_id']}` reason=`{item['reason']}`")
        for kind in EVAL_KINDS:
            if entry.get(kind):
                lines.append(f"- {kind} hash: `{entry[kind]['sha256']}`")
    return lines
