from typing import Any, Callable, Dict, Optional

from ..guardrails.tool_guardrail import ToolGuardrail
from ..policies import POLICY_DATA_ACCESS
from .crm import (
    analyze_account_risk,
    list_open_opportunities,
    lookup_account,
    lookup_account_context,
    summarize_pipeline,
    summarize_tickets,
)
from .email import draft_email, send_email, set_email_approval
from .restricted import lookup_internal_financial_data, lookup_internal_hr_data
from .sandbox import analyze_crm_data

TOOL_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "lookup_account": lookup_account,
    "lookup_account_context": lookup_account_context,
    "list_open_opportunities": list_open_opportunities,
    "summarize_pipeline": summarize_pipeline,
    "summarize_tickets": summarize_tickets,
    "analyze_account_risk": analyze_account_risk,
    "analyze_data_safely": analyze_crm_data,
    "draft_email": draft_email,
    "send_email": send_email,
    "lookup_internal_hr_data": lookup_internal_hr_data,
    "lookup_internal_financial_data": lookup_internal_financial_data,
}

_tool_guardrail = ToolGuardrail()


def execute_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    approval: Optional[str] = None,
) -> Dict[str, Any]:
    """Single chokepoint: every tool call is checked before execution."""
    arguments = arguments or {}
    allowed, reason, metadata = _tool_guardrail.check_tool_call(name, arguments, approval=approval)
    if not allowed:
        return {
            "name": name,
            "status": "blocked",
            "reason": reason,
            "policy": (metadata or {}).get("policy", POLICY_DATA_ACCESS),
            "output": None,
            "metadata": metadata or {},
        }

    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {
            "name": name,
            "status": "error",
            "reason": f"unknown_tool:{name}",
            "policy": None,
            "output": None,
        }

    try:
        output = func(**arguments)
    except TypeError:
        output = func() if not arguments else func(**{k: v for k, v in arguments.items() if v is not None})

    if isinstance(output, dict) and output.get("status") in {"blocked", "error"}:
        return {
            "name": name,
            "status": output.get("status"),
            "reason": output.get("reason"),
            "policy": output.get("policy"),
            "output": output.get("output"),
            "metadata": metadata or {},
        }

    return {
        "name": name,
        "status": "success",
        "reason": None,
        "policy": None,
        "output": output,
        "metadata": metadata or {},
    }


def get_tools(*_args, **_kwargs):
    return list(TOOL_FUNCTIONS.values())


def set_hitl_manager(_manager) -> None:
    """Kept for compatibility; approval is passed per request."""
    return None
