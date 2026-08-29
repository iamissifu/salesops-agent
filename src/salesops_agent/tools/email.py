import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..config.settings import settings
from ..guardrails.tool_guardrail import ToolGuardrail
from ..policies import POLICY_EMAIL
from .crm import lookup_account_context

_CURRENT_APPROVAL: Optional[str] = None
_guardrail = ToolGuardrail()


def set_email_approval(approval: Optional[str]) -> None:
    global _CURRENT_APPROVAL
    _CURRENT_APPROVAL = approval


def get_email_approval() -> Optional[str]:
    return _CURRENT_APPROVAL


def draft_email(account_name_or_id: str, purpose: str = "follow-up") -> Dict[str, Any]:
    context = lookup_account_context(account_name_or_id)
    if "error" in context:
        return context

    account = context.get("account", {})
    contacts = context.get("contacts", [])
    primary = next((c for c in contacts if c.get("is_primary")), contacts[0] if contacts else None)
    if not primary:
        return {"error": f"No contact found for account {account.get('name', 'Unknown')}"}

    first_name = primary.get("first_name", "Team")
    return {
        "to": primary.get("email"),
        "to_name": f"{primary.get('first_name', '')} {primary.get('last_name', '')}".strip(),
        "subject": f"Following up on {account.get('name', 'your account')}",
        "body": (
            f"Hi {first_name},\n\n"
            f"I wanted to follow up regarding {purpose}.\n\n"
            "Please let me know if you have any questions.\n\n"
            "Best regards,\n"
            "UdaCenture Sales Team"
        ),
        "status": "drafted",
        "requires_approval": True,
    }


def send_email(to: str, subject: str, body: str, approval: Optional[str] = None) -> Dict[str, Any]:
    """Send is gated by the tool guardrail. Direct calls without approval cannot succeed."""
    decision = approval if approval is not None else _CURRENT_APPROVAL
    allowed, reason, metadata = _guardrail.check_tool_call(
        "send_email",
        {"to": to, "subject": subject, "body": body},
        approval=decision,
    )
    if not allowed:
        return {
            "status": "blocked",
            "reason": reason,
            "policy": (metadata or {}).get("policy", POLICY_EMAIL),
            "output": None,
        }

    outbox_path = settings.data_dir / "email_outbox.json"
    if outbox_path.exists():
        with open(outbox_path, "r", encoding="utf-8") as handle:
            outbox = json.load(handle)
    else:
        outbox = []

    message = {
        "to": to,
        "subject": subject,
        "body": body,
        "status": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    outbox.append(message)
    with open(outbox_path, "w", encoding="utf-8") as handle:
        json.dump(outbox, handle, indent=2)

    return {"status": "sent", "message": message}
