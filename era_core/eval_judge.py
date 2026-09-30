"""Judge audit for BDS-ERA-EVAL-v0.1 (WP09).

ERA never calls a judge. An external harness writes a ``JudgeEvidence.v1`` file
into the target tree. ERA audits it. A judge-derived quality metric counts toward
a quality gate only when the audit passed. The judge is evidence, never truth.

Evidence file::

    {
      "schema_version": "JudgeEvidence.v1",
      "judge":   {"model_family": "family-a", "model_id": "...", "prompt_hash": "..."},
      "subject": {"model_family": "family-b"},
      "items": [
        {"item_id": "1", "winner_ab": "candidate", "winner_ba": "candidate",
         "human_label": "candidate"}            # human_label only on the calibration subset
      ]
    }

``winner_ab`` and ``winner_ba`` are the verdicts from the two presentation orders,
already mapped back to ``candidate``, ``baseline``, or ``tie``.

Policy (``quality_gate_policy.judge_policy``)::

    {"judge_metrics": ["helpfulness"], "judge_evidence_path": "judge/evidence.json",
     "min_items": 20, "min_position_consistency": 0.8,
     "min_calibration_items": 10, "min_human_agreement": 0.8,
     "require_family_separation": true}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from era_core.artifact_paths import utc_now_text
from era_core.eval_contracts import _check_enum, _check_hash, _check_required, _check_schema, _seal
from era_core.hashing import sha256_path

JUDGE_EVIDENCE_SCHEMA = "JudgeEvidence.v1"
JUDGE_AUDIT_SCHEMA = "JudgeAuditArtifact.v1"
VERDICTS = ("candidate", "baseline", "tie")
AUDIT_STATUSES = frozenset({"passed", "failed", "unproven", "invalid"})
MAX_LISTED_DISAGREEMENTS = 50

DEFAULT_THRESHOLDS = {
    "min_items": 20,
    "min_position_consistency": 0.8,
    "min_calibration_items": 10,
    "min_human_agreement": 0.8,
    "require_family_separation": True,
}


def validate_judge_policy(policy: Any) -> list[str]:
    if not isinstance(policy, dict):
        return ["quality_gate_policy.judge_policy must be an object."]
    errors: list[str] = []
    metrics = policy.get("judge_metrics")
    if not isinstance(metrics, list) or not metrics or any(not isinstance(m, str) for m in metrics):
        errors.append("judge_policy.judge_metrics must list at least one metric name.")
    if not isinstance(policy.get("judge_evidence_path"), str) or not policy["judge_evidence_path"]:
        errors.append("judge_policy needs judge_evidence_path.")
    for key in ("min_items", "min_calibration_items"):
        value = policy.get(key, DEFAULT_THRESHOLDS[key])
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"judge_policy.{key} must be a positive integer.")
    for key in ("min_position_consistency", "min_human_agreement"):
        value = policy.get(key, DEFAULT_THRESHOLDS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append(f"judge_policy.{key} must be a number from 0 to 1.")
    if not isinstance(policy.get("require_family_separation", True), bool):
        errors.append("judge_policy.require_family_separation must be true or false.")
    return errors


def thresholds_from(policy: dict[str, Any]) -> dict[str, Any]:
    return {key: policy.get(key, default) for key, default in DEFAULT_THRESHOLDS.items()}


def read_judge_evidence(
    repo_path: Path, cwd_subpath: str, relative: str
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    root = repo_path.resolve()
    target = ((root / cwd_subpath) / relative).resolve()
    if target != root and root not in target.parents:
        return None, None, [f"judge_evidence_path `{relative}` escapes the target repository."]
    if not target.is_file():
        return None, None, [f"Judge evidence file `{relative}` does not exist."]
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, [f"Judge evidence file `{relative}` is not valid JSON."]
    if not isinstance(payload, dict) or payload.get("schema_version") != JUDGE_EVIDENCE_SCHEMA:
        return None, None, [f"Judge evidence file `{relative}` is not {JUDGE_EVIDENCE_SCHEMA}."]
    if not isinstance(payload.get("judge"), dict) or not isinstance(payload.get("items"), list):
        return None, None, [f"Judge evidence file `{relative}` needs judge and items."]
    return payload, sha256_path(target), []


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters. None when it is undefined (one category only)."""
    if not pairs:
        return None
    total = len(pairs)
    categories = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    observed = sum(1 for a, b in pairs if a == b) / total
    expected = sum(
        (sum(1 for a, _ in pairs if a == c) / total) * (sum(1 for _, b in pairs if b == c) / total)
        for c in categories
    )
    if expected == 1:
        return None
    return round((observed - expected) / (1 - expected), 4)


def analyze_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Compute consistency, human agreement, and the full disagreement list.

    An item without both orders is unpaired and left out of the rates. It is still
    listed. Disagreements are kept, never averaged away.
    """
    paired: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    unpaired = 0
    for item in evidence["items"]:
        if not isinstance(item, dict) or not item.get("item_id"):
            unpaired += 1
            disagreements.append({"item_id": None, "kind": "malformed_item"})
            continue
        ab, ba = item.get("winner_ab"), item.get("winner_ba")
        if ab not in VERDICTS or ba not in VERDICTS:
            unpaired += 1
            disagreements.append({"item_id": item["item_id"], "kind": "unpaired_order", "winner_ab": ab, "winner_ba": ba})
            continue
        paired.append(item)
        if ab != ba:
            disagreements.append(
                {"item_id": item["item_id"], "kind": "position_flip", "winner_ab": ab, "winner_ba": ba}
            )

    consistent = [item for item in paired if item["winner_ab"] == item["winner_ba"]]
    calibration = [item for item in paired if item.get("human_label") in VERDICTS]
    pairs: list[tuple[str, str]] = []
    for item in calibration:
        verdict = item["winner_ab"] if item["winner_ab"] == item["winner_ba"] else "inconsistent"
        pairs.append((verdict, item["human_label"]))
        if verdict != item["human_label"] and item["winner_ab"] == item["winner_ba"]:
            disagreements.append(
                {"item_id": item["item_id"], "kind": "human_disagreement", "judge": verdict, "human_label": item["human_label"]}
            )
    agreement = sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else None
    judge = evidence["judge"]
    subject = evidence.get("subject") if isinstance(evidence.get("subject"), dict) else {}
    return {
        "counts": {
            "items": len(evidence["items"]),
            "paired_items": len(paired),
            "unpaired_items": unpaired,
            "consistent_items": len(consistent),
            "calibration_items": len(calibration),
        },
        "position_consistency": round(len(consistent) / len(paired), 4) if paired else None,
        "human_agreement": round(agreement, 4) if agreement is not None else None,
        "cohens_kappa": cohens_kappa(pairs),
        "judge": {k: judge.get(k) for k in ("model_family", "model_id", "prompt_hash")},
        "subject_family": subject.get("model_family"),
        "disagreements": disagreements,
    }


def evaluate_audit(analysis: dict[str, Any], thresholds: dict[str, Any]) -> tuple[str, list[str]]:
    """Return ``(audit_status, reasons)``. Thin evidence is ``unproven``. A missed bar is ``failed``."""
    counts = analysis["counts"]
    unproven: list[str] = []
    failed: list[str] = []
    judge_family = analysis["judge"].get("model_family")
    subject_family = analysis["subject_family"]
    if thresholds["require_family_separation"]:
        if not judge_family or not subject_family:
            unproven.append("Judge or subject model family is not declared, so separation is unproven.")
        elif judge_family == subject_family:
            failed.append(f"Judge and subject share the model family `{judge_family}`.")
    if counts["paired_items"] < thresholds["min_items"]:
        unproven.append(f"{counts['paired_items']} paired items is below the minimum {thresholds['min_items']}.")
    elif analysis["position_consistency"] < thresholds["min_position_consistency"]:
        failed.append(
            f"Position consistency {analysis['position_consistency']} is below {thresholds['min_position_consistency']}."
        )
    if counts["calibration_items"] < thresholds["min_calibration_items"]:
        unproven.append(
            f"{counts['calibration_items']} human-labelled items is below the minimum {thresholds['min_calibration_items']}."
        )
    elif analysis["human_agreement"] < thresholds["min_human_agreement"]:
        failed.append(f"Human agreement {analysis['human_agreement']} is below {thresholds['min_human_agreement']}.")
    if failed:
        return "failed", failed + unproven
    if unproven:
        return "unproven", unproven
    return "passed", []


def build_judge_audit(
    *,
    fingerprint: dict[str, Any],
    evidence: dict[str, Any] | None,
    read_problems: list[str],
    thresholds: dict[str, Any],
    judge_metrics: list[str],
    raw_evidence_refs: list[str],
    created_at: str | None = None,
) -> dict[str, Any]:
    if evidence is None:
        analysis = {
            "counts": {"items": 0, "paired_items": 0, "unpaired_items": 0, "consistent_items": 0, "calibration_items": 0},
            "position_consistency": None,
            "human_agreement": None,
            "cohens_kappa": None,
            "judge": {"model_family": None, "model_id": None, "prompt_hash": None},
            "subject_family": None,
            "disagreements": [],
        }
        status, reasons = "invalid", read_problems
    else:
        analysis = analyze_evidence(evidence)
        status, reasons = evaluate_audit(analysis, thresholds)
    disagreements = analysis["disagreements"]
    return _seal(
        {
            "schema_version": JUDGE_AUDIT_SCHEMA,
            "judge_audit_id": f"judge_audit:{fingerprint['workload_id']}:{fingerprint['run_id']}",
            "run_id": fingerprint["run_id"],
            "workload_id": fingerprint["workload_id"],
            "config_fingerprint_id": fingerprint["fingerprint_id"],
            "config_fingerprint_sha256": fingerprint["sha256"],
            "authority": "evidence_only",
            "judge_metrics": judge_metrics,
            "judge": analysis["judge"],
            "subject_family": analysis["subject_family"],
            "counts": analysis["counts"],
            "position_consistency": analysis["position_consistency"],
            "human_agreement": analysis["human_agreement"],
            "cohens_kappa": analysis["cohens_kappa"],
            "thresholds": thresholds,
            "audit_status": status,
            "failure_reasons": reasons,
            "disagreement_total": len(disagreements),
            "disagreements": disagreements[:MAX_LISTED_DISAGREEMENTS],
            "disagreements_truncated": len(disagreements) > MAX_LISTED_DISAGREEMENTS,
            "raw_evidence_refs": raw_evidence_refs,
            "created_at": created_at or utc_now_text(),
        }
    )


def validate_judge_audit(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = "JudgeAuditArtifact"
    if not _check_schema(payload, JUDGE_AUDIT_SCHEMA, errors):
        return errors
    _check_required(
        payload,
        (
            "judge_audit_id", "run_id", "workload_id", "config_fingerprint_id", "config_fingerprint_sha256",
            "authority", "judge_metrics", "judge", "counts", "thresholds", "audit_status", "failure_reasons",
            "disagreement_total", "disagreements", "raw_evidence_refs", "created_at",
        ),
        label,
        errors,
    )
    _check_enum(payload, "audit_status", AUDIT_STATUSES, label, errors)
    if payload.get("authority") != "evidence_only":
        errors.append(f"{label} authority must be `evidence_only`. A judge is never canonical truth.")
    if not errors:
        if payload["audit_status"] != "passed" and not payload["failure_reasons"]:
            errors.append(f"{label} with status `{payload['audit_status']}` must list failure_reasons.")
        if payload["audit_status"] in {"passed", "failed", "unproven"}:
            analysis = {
                "counts": payload["counts"],
                "position_consistency": payload.get("position_consistency"),
                "human_agreement": payload.get("human_agreement"),
                "judge": payload["judge"],
                "subject_family": payload.get("subject_family"),
            }
            try:
                expected, _ = evaluate_audit(analysis, payload["thresholds"])
            except (KeyError, TypeError):
                expected = None
                errors.append(f"{label} thresholds or counts are malformed.")
            if expected is not None and expected != payload["audit_status"]:
                errors.append(f"{label} audit_status `{payload['audit_status']}` contradicts its numbers (`{expected}`).")
        if payload["disagreement_total"] < len(payload["disagreements"]):
            errors.append(f"{label} lists more disagreements than its total.")
    _check_hash(payload, label, errors)
    return errors
