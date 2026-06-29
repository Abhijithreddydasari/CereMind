"""Tool registry: strict JSON schemas, specialist grouping, risk tiers, dispatch."""
from __future__ import annotations

import inspect
from typing import Any, Callable

from app.agents.schemas import RiskTier
from app.tools import changes, knowledge, remediation, telemetry


def _tool(name: str, description: str, properties: dict[str, Any],
          required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


# --------------------------------------------------------------------------- #
# Investigation tools, grouped by specialist
# --------------------------------------------------------------------------- #
TELEMETRY_TOOLS = [
    _tool("get_job_runs", "List recent runs of a pipeline job with status.",
          {"job_id": {"type": "string"}, "limit": {"type": "integer"}}, ["job_id"]),
    _tool("get_job_logs", "Fetch task logs for a run (defaults to the latest failed run).",
          {"run_id": {"type": "string"}, "task_id": {"type": "string"}}, []),
    _tool("get_metrics", "Get a metric time series for a task (e.g. memory_mb).",
          {"task_id": {"type": "string"}, "metric": {"type": "string"}}, ["task_id"]),
]

CHANGE_TOOLS = [
    _tool("list_recent_config_changes", "List recent pipeline config changes, newest first.",
          {"limit": {"type": "integer"}}, []),
    _tool("config_diff", "Show the diff and metadata for a config change id.",
          {"change_id": {"type": "string"}}, ["change_id"]),
]

KNOWLEDGE_TOOLS = [
    _tool("query_runbook", "Permission-aware search of runbooks/docs for a query.",
          {"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"]),
    _tool("find_similar_failures", "Find similar past incidents/post-mortems for a query.",
          {"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"]),
]

SPECIALIST_TOOLS: dict[str, list[dict[str, Any]]] = {
    "telemetry": TELEMETRY_TOOLS,
    "change": CHANGE_TOOLS,
    "knowledge": KNOWLEDGE_TOOLS,
}

# --------------------------------------------------------------------------- #
# Dispatch table + risk tiers
# --------------------------------------------------------------------------- #
_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    # read-only (tier 0)
    "get_job_runs": telemetry.get_job_runs,
    "get_job_logs": telemetry.get_job_logs,
    "get_metrics": telemetry.get_metrics,
    "list_recent_config_changes": changes.list_recent_config_changes,
    "config_diff": changes.config_diff,
    "query_runbook": knowledge.query_runbook,
    "find_similar_failures": knowledge.find_similar_failures,
    # remediation
    "revert_config": remediation.revert_config,
    "retry_with_params": remediation.retry_with_params,
    "rerun_job": remediation.rerun_job,
    "create_ticket": remediation.create_ticket,
    "post_to_slack": remediation.post_to_slack,
}

RISK_TIERS: dict[str, int] = {
    "get_job_runs": RiskTier.READ_ONLY.value,
    "get_job_logs": RiskTier.READ_ONLY.value,
    "get_metrics": RiskTier.READ_ONLY.value,
    "list_recent_config_changes": RiskTier.READ_ONLY.value,
    "config_diff": RiskTier.READ_ONLY.value,
    "query_runbook": RiskTier.READ_ONLY.value,
    "find_similar_failures": RiskTier.READ_ONLY.value,
    "create_ticket": RiskTier.LOW_REVERSIBLE.value,
    "post_to_slack": RiskTier.LOW_REVERSIBLE.value,
    "retry_with_params": RiskTier.HIGH.value,
    "revert_config": RiskTier.HIGH.value,
    "rerun_job": RiskTier.HIGH.value,
}

SPECIALIST_OF: dict[str, str] = {}
for _spec, _tools in SPECIALIST_TOOLS.items():
    for _t in _tools:
        SPECIALIST_OF[_t["function"]["name"]] = _spec


def risk_tier(name: str) -> int:
    return RISK_TIERS.get(name, RiskTier.HIGH.value)


def _filter_args(fn: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any]:
    """Keep only kwargs the function actually accepts.

    LLM-proposed actions sometimes include extra/aliased fields (e.g. a `run_id`
    on rerun_job). We drop unknown kwargs rather than crash, and map a few common
    aliases so a well-intentioned-but-imprecise call still succeeds.
    """
    sig = inspect.signature(fn)
    params = sig.parameters
    # If the function takes **kwargs, pass everything through.
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(args)

    # Map common arg-name variants the model may emit to the real parameter.
    rename = {"dag_id": "job_id", "job": "job_id", "pipeline_id": "job_id",
              "run": "run_id", "id": "change_id"}
    fold_into_params = {"memory_mb", "worker_memory_mb"}

    cleaned: dict[str, Any] = {}
    for k, v in args.items():
        key = rename.get(k, k)
        if key in params:
            cleaned[key] = v
        elif k in fold_into_params and "params" in params:
            cleaned.setdefault("params", {})
            if isinstance(cleaned["params"], dict):
                cleaned["params"][k] = v
    return cleaned


def dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**_filter_args(fn, args or {}))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{name} failed: {e}"}
