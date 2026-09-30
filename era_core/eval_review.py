"""Load and render quality-gated evaluation evidence for review.md (WP05)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.eval_telemetry import ENERGY_SCOPES

EVAL_KINDS = ("fingerprint", "quality_gate", "metric_vector", "judge_audit", "isolation_receipt", "baseline_snapshot", "comparison")


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


def _isolation_lines(receipt: dict[str, Any]) -> list[str]:
    posture = receipt.get("posture") or {}
    lines = [
        f"- isolation: `{receipt['status']}` (provider `{receipt.get('provider')}`)",
        f"  - sandbox `{_fmt(posture.get('sandbox'))}`, network `{_fmt(posture.get('network'))}`,"
        f" target filesystem `{_fmt(posture.get('target_filesystem'))}`, trust `{_fmt(posture.get('target_trust'))}`",
    ]
    if receipt.get("isolation_required"):
        lines.append(f"  - required because: {', '.join(receipt.get('required_reasons', []))}")
    if receipt["status"] == "unsatisfied":
        lines.append("  - no claim is made: the run was not contained")
    for limitation in receipt.get("limitations", []):
        lines.append(f"  - limitation: {limitation}")
    return lines


def _judge_lines(audit: dict[str, Any]) -> list[str]:
    judge = audit.get("judge") or {}
    counts = audit.get("counts") or {}
    lines = [
        f"- judge audit: `{audit['audit_status']}` (evidence only, never canonical truth)",
        f"  - judge family `{_fmt(judge.get('model_family'))}`, subject family `{_fmt(audit.get('subject_family'))}`",
        f"  - paired items `{counts.get('paired_items', 0)}`, position consistency `{_fmt(audit.get('position_consistency'))}`",
        f"  - human-labelled items `{counts.get('calibration_items', 0)}`, agreement `{_fmt(audit.get('human_agreement'))}`,"
        f" kappa `{_fmt(audit.get('cohens_kappa'))}`",
        f"  - disagreements kept: `{audit.get('disagreement_total', 0)}`"
        + (" (list truncated)" if audit.get("disagreements_truncated") else ""),
    ]
    for reason in audit.get("failure_reasons", []):
        lines.append(f"  - audit reason: {reason}")
    for item in (audit.get("disagreements") or [])[:5]:
        lines.append(f"  - disagreement `{item.get('item_id')}` kind=`{item.get('kind')}`")
    if audit["audit_status"] != "passed":
        lines.append(f"  - judge metrics not admitted to the quality gate: `{', '.join(audit.get('judge_metrics', []))}`")
    return lines


def _interval_text(interval: dict[str, Any] | None) -> str:
    if not interval:
        return "`not available`"
    return f"`[{interval['ci_low']}, {interval['ci_high']}]`"


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
        receipt = found.get("isolation_receipt")
        if receipt is not None:
            lines.extend(_isolation_lines(receipt))
        audit = found.get("judge_audit")
        if audit is not None:
            lines.extend(_judge_lines(audit))
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
        primary = (comparison or {}).get("primary_metric", "median_ms")
        lines.append(f"- primary metric (the claim rests on this one only): `{primary}`")
        lines.extend(
            [
                "",
                "| metric | direction | candidate | baseline | delta | delta % | outcome |",
                "|---|---|---:|---:|---:|---:|---|",
            ]
        )
        if deltas:
            for name, delta in sorted(deltas.items()):
                label = f"{name} (primary)" if name == primary else name
                lines.append(
                    f"| {label} | {delta['direction']} | {delta['candidate']} | {delta['baseline']} |"
                    f" {delta['delta']} | {delta['delta_pct']} | {delta.get('outcome', 'n/a')} |"
                )
        else:
            lines.append("| none | n/a | n/a | n/a | n/a | n/a | n/a |")
        primary_delta = deltas.get(primary)
        if primary_delta is not None:
            lines.append(
                "- uncertainty (bootstrap median, 95 percent):"
                f" candidate {_interval_text(primary_delta.get('candidate_interval'))},"
                f" baseline {_interval_text(primary_delta.get('baseline_interval'))}"
            )
        for name, metric in sorted(((vector or {}).get("metrics") or {}).items()):
            if metric.get("scope"):
                lines.append(
                    f"- energy scope for `{name}`: `{metric['scope']}` ({ENERGY_SCOPES.get(metric['scope'], 'unknown scope')})"
                )
        warmup = ((vector or {}).get("variance_or_uncertainty") or {}).get("warmup_iterations")
        if warmup:
            lines.append(f"- warmup iterations discarded: `{warmup}`")
        for problem in entry.get("telemetry_problems", []):
            lines.append(f"- telemetry problem: {problem}")
        for problem in entry.get("agent_problems", []):
            lines.append(f"- agent evidence problem: {problem}")
        for note in entry.get("telemetry_notes", []):
            lines.append(f"- telemetry note: {note}")
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
