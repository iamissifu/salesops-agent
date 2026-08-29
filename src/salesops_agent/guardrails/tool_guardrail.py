from typing import Any, Dict, Optional, Tuple

from ..policies import POLICY_DATA_ACCESS, POLICY_EMAIL

RESTRICTED_TOOLS = {
    "lookup_internal_hr_data",
    "lookup_internal_financial_data",
    "get_internal_hr_data",
    "get_internal_financial_data",
}

EMAIL_TOOLS = {"send_email"}


class ToolGuardrail:
    """Application-level policy check applied to every proposed tool call."""

    def check_tool_call(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        approval: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        tool_args = tool_args or {}

        if tool_name in RESTRICTED_TOOLS:
            return False, "restricted_internal_data", {
                "tool": tool_name,
                "policy": POLICY_DATA_ACCESS,
                "layer": "tool",
                "severity": "high",
            }

        if tool_name in EMAIL_TOOLS:
            if approval == "approve":
                return True, None, {
                    "tool": tool_name,
                    "requires_approval": True,
                    "hitl_decision": "approved",
                    "policy": POLICY_EMAIL,
                    "layer": "hitl",
                }
            reason = "hitl_rejected" if approval == "reject" else "hitl_approval_required"
            return False, reason, {
                "tool": tool_name,
                "policy": POLICY_EMAIL,
                "layer": "hitl",
                "hitl_decision": "rejected",
            }

        return True, None, {"tool": tool_name, "layer": "tool"}
