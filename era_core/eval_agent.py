"""Agent efficiency for BDS-ERA-EVAL-v0.1 (WP10).

ERA does not run an agent. An external harness runs the tasks and writes an
``AgentRunEvidence.v1`` file into the target tree. ERA summarizes it into metric
vectors. Cost per successful task and joules per successful task are vector
metrics. They are never promotion scores.

Evidence file::

    {"schema_version": "AgentRunEvidence.v1", "measurement_scope": "agent_harness",
     "energy": {"scope": "system_wall"},                 # only when energy is reported
     "tasks": [{"task_id": "t1", "success": true, "steps": 7, "tool_calls": 4,
                "input_tokens": 1200, "output_tokens": 300, "wall_time_ms": 8200,
                "api_cost_usd": 0.021, "energy_joules": 130.0}]}   # cost and energy optional

Manifest block (inside ``evaluation``, with ``subject_kind: "agent"``)::

    "agent_policy": {"agent_evidence_path": "agent/runs.json", "energy_scope": "system_wall"}
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from era_core.eval_stats import bootstrap_median_ci, bootstrap_ratio_ci, wilson_interval
from era_core.eval_telemetry import ENERGY_SCOPES
from era_core.hashing import sha256_path

AGENT_EVIDENCE_SCHEMA = "AgentRunEvidence.v1"
SUCCESS_METRIC = "task_success_rate"

AGENT_METRICS: dict[str, str] = {
    "task_success_rate": "ratio",
    "steps_per_task": "steps",
    "tool_calls_per_task": "calls",
    "tokens_per_task": "tokens",
    "wall_time_ms_per_task": "ms",
    "api_cost_usd_per_successful_task": "USD/task",
    "joules_per_successful_task": "J/task",
}
# What an agent workload must declare about the agent itself (plan section 04).
AGENT_SUBJECT_FIELDS = (
    "agent_revision",
    "model_lane",
    "tool_policy_hash",
    "prompt_program_hash",
    "step_budget",
    "token_budget",
)
TASK_INT_FIELDS = ("steps", "tool_calls", "input_tokens", "output_tokens", "wall_time_ms")
# Marks a metric whose spread is between tasks, not measurement noise. Stability
# then rests on min_samples and interval separation, not on the timing CV rule.
TASK_LEVEL = "task_level"


def validate_agent_policy(policy: Any, subject_kind: Any, subject_identity: Any) -> list[str]:
    errors: list[str] = []
    if subject_kind != "agent":
        errors.append("evaluation.agent_policy needs subject_kind `agent`.")
    if not isinstance(policy, dict):
        return errors + ["evaluation.agent_policy must be an object."]
    if not isinstance(policy.get("agent_evidence_path"), str) or not policy["agent_evidence_path"]:
        errors.append("evaluation.agent_policy needs agent_evidence_path.")
    if "energy_scope" in policy and policy["energy_scope"] not in ENERGY_SCOPES:
        errors.append(f"evaluation.agent_policy.energy_scope must be one of {sorted(ENERGY_SCOPES)}.")
    return errors


def validate_agent_subject(subject_identity: Any) -> list[str]:
    identity = subject_identity if isinstance(subject_identity, dict) else {}
    return [
        f"evaluation.subject_identity is missing `{field}` (required for an agent)."
        for field in AGENT_SUBJECT_FIELDS
        if identity.get(field) in (None, "")
    ]


def read_agent_evidence(
    repo_path: Path, cwd_subpath: str, relative: str
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    root = repo_path.resolve()
    target = ((root / cwd_subpath) / relative).resolve()
    if target != root and root not in target.parents:
        return None, None, [f"agent_evidence_path `{relative}` escapes the target repository."]
    if not target.is_file():
        return None, None, [f"Agent evidence file `{relative}` does not exist."]
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, [f"Agent evidence file `{relative}` is not valid JSON."]
    if not isinstance(payload, dict) or payload.get("schema_version") != AGENT_EVIDENCE_SCHEMA:
        return None, None, [f"Agent evidence file `{relative}` is not {AGENT_EVIDENCE_SCHEMA}."]
    if not isinstance(payload.get("tasks"), list) or not isinstance(payload.get("measurement_scope"), str):
        return None, None, [f"Agent evidence file `{relative}` needs tasks and measurement_scope."]
    return payload, sha256_path(target), []


def _number(value: Any, integer: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int,) if integer else (int, float)):
        return False
    return math.isfinite(value) and value >= 0


def _valid_tasks(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    tasks: list[dict[str, Any]] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, task in enumerate(payload["tasks"]):
        name = task.get("task_id") if isinstance(task, dict) else None
        if not isinstance(task, dict) or not name or name in seen or not isinstance(task.get("success"), bool):
            problems.append(f"Task #{index} is malformed or repeats a task_id and was left out.")
            continue
        if not all(_number(task.get(field), integer=True) for field in TASK_INT_FIELDS):
            problems.append(f"Task `{name}` has a missing or invalid count and was left out.")
            continue
        seen.add(name)
        tasks.append(task)
    return tasks, problems


def summarize_agent(payload: dict[str, Any], directions: dict[str, str], agent_policy: dict[str, Any]) -> dict[str, Any]:
    """Turn task records into metric entries.

    A metric is left out, with a named problem, when its inputs are missing. Cost
    per successful task needs a cost on every task. Joules per successful task
    needs energy on every task and a matching declared scope.
    """
    tasks, problems = _valid_tasks(payload)
    notes: list[str] = []
    metrics: dict[str, dict[str, Any]] = {}
    uncertainty: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total = len(tasks)
    successes = [1 if task["success"] else 0 for task in tasks]
    won = sum(successes)
    result = {
        "metrics": metrics,
        "per_metric_variance": {},
        "per_metric_sample_count": counts,
        "uncertainty": uncertainty,
        "problems": problems,
        "notes": notes,
        "success_rate": (won / total) if total else None,
        "task_count": total,
    }
    if not total:
        problems.append("Agent evidence has no valid tasks.")
        return result

    def add(name: str, value: float, interval: dict[str, Any] | None, why: str) -> None:
        if name not in directions:
            return
        metrics[name] = {"value": value, "unit": AGENT_METRICS[name], "direction": directions[name], "aggregation": why}
        uncertainty[name] = interval or {"omitted": f"{total} tasks is too few for an interval."}
        counts[name] = total
        result["per_metric_variance"][name] = TASK_LEVEL

    def median_of(name: str, values: list[float], label: str) -> None:
        add(name, statistics.median(values), bootstrap_median_ci([float(v) for v in values]), label)

    add(SUCCESS_METRIC, won / total, wilson_interval(won, total), "success_share")
    median_of("steps_per_task", [t["steps"] for t in tasks], "median_over_tasks")
    median_of("tool_calls_per_task", [t["tool_calls"] for t in tasks], "median_over_tasks")
    median_of("tokens_per_task", [t["input_tokens"] + t["output_tokens"] for t in tasks], "median_over_tasks")
    median_of("wall_time_ms_per_task", [t["wall_time_ms"] for t in tasks], "median_over_tasks")

    def per_success(name: str, field: str, integer: bool = False) -> None:
        if name not in directions:
            return
        values = [t.get(field) for t in tasks]
        if not all(_number(v, integer) for v in values):
            problems.append(f"Metric `{name}` left out: `{field}` is missing or invalid on some tasks.")
            return
        if won == 0:
            problems.append(f"Metric `{name}` left out: no task succeeded, so the ratio is undefined.")
            return
        add(name, sum(values) / won, bootstrap_ratio_ci([float(v) for v in values], successes), "total_over_successes")

    per_success("api_cost_usd_per_successful_task", "api_cost_usd")
    if "joules_per_successful_task" in directions:
        declared = agent_policy.get("energy_scope")
        reported = (payload.get("energy") or {}).get("scope") if isinstance(payload.get("energy"), dict) else None
        if declared not in ENERGY_SCOPES:
            problems.append("Metric `joules_per_successful_task` left out: agent_policy.energy_scope is not declared.")
        elif reported != declared:
            problems.append(
                f"Metric `joules_per_successful_task` left out: energy scope mismatch (declared `{declared}`, reported `{reported}`)."
            )
        else:
            per_success("joules_per_successful_task", "energy_joules")
            if "joules_per_successful_task" in metrics:
                metrics["joules_per_successful_task"]["scope"] = declared
    return result
