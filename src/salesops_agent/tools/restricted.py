from typing import Any, Dict, Optional

from ..guardrails.tool_guardrail import ToolGuardrail
from ..policies import POLICY_DATA_ACCESS

_guardrail = ToolGuardrail()


def lookup_internal_hr_data(query: Optional[str] = None) -> Dict[str, Any]:
    """Restricted HR tool. The policy layer blocks this before any data is read."""
    allowed, reason, metadata = _guardrail.check_tool_call(
        "lookup_internal_hr_data",
        {"query": query},
    )
    if not allowed:
        return {
            "status": "blocked",
            "reason": reason or "restricted_internal_data",
            "policy": (metadata or {}).get("policy", POLICY_DATA_ACCESS),
            "output": None,
        }
    return {
        "status": "blocked",
        "reason": "restricted_internal_data",
        "policy": POLICY_DATA_ACCESS,
        "output": None,
    }


def lookup_internal_financial_data(query: Optional[str] = None) -> Dict[str, Any]:
    """Restricted financial-strategy tool. Blocked before any data is read."""
    allowed, reason, metadata = _guardrail.check_tool_call(
        "lookup_internal_financial_data",
        {"query": query},
    )
    if not allowed:
        return {
            "status": "blocked",
            "reason": reason or "restricted_internal_data",
            "policy": (metadata or {}).get("policy", POLICY_DATA_ACCESS),
            "output": None,
        }
    return {
        "status": "blocked",
        "reason": "restricted_internal_data",
        "policy": POLICY_DATA_ACCESS,
        "output": None,
    }
