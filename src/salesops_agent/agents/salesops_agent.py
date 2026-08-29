import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..config.settings import settings
from ..guardrails.input_guardrail import InputGuardrail
from ..guardrails.output_guardrail import OutputGuardrail
from ..guardrails.tool_guardrail import ToolGuardrail
from ..hitl.manager import HITLManager
from ..logging.structured_logger import StructuredLogger, TraceWriter
from ..policies import POLICY_EMAIL, POLICY_INPUT, POLICY_OUTPUT
from ..prompts.prompt_manager import PromptManager
from ..tools import execute_tool
from ..tools.email import set_email_approval
from ..utils.account_resolver import AccountResolver

APPROVED_SANDBOX_ANALYSIS = """
closed = {'Closed Won', 'Closed Lost'}
by_stage = {}
open_amounts = []
for opp in opportunities:
    stage = opp.get('stage', 'Unknown')
    amount = opp.get('amount_usd', 0) or 0
    bucket = by_stage.setdefault(stage, {'count': 0, 'amount_usd': 0})
    bucket['count'] += 1
    bucket['amount_usd'] += amount
    if stage not in closed:
        open_amounts.append(amount)

severity = {}
open_tickets = []
for ticket in tickets:
    sev = ticket.get('severity', 'unknown')
    severity[sev] = severity.get(sev, 0) + 1
    if ticket.get('status') in {'open', 'in_progress'}:
        open_tickets.append(ticket)

high_risk = []
for account in accounts:
    health = account.get('health_score') or 0
    end = account.get('contract_end') or account.get('contract_end_date')
    if health < 50:
        high_risk.append({'name': account.get('name'), 'health_score': health, 'renewal': end})

result = {
    'pipeline_by_stage': by_stage,
    'open_opportunity_count': len(open_amounts),
    'average_deal_size': (sum(open_amounts) / len(open_amounts)) if open_amounts else 0,
    'ticket_severity': severity,
    'open_ticket_count': len(open_tickets),
    'high_risk_renewals': high_risk[:10],
}
"""


def _estimate_cost(user_input: str, output: str) -> float:
    input_tokens = max(1, len(user_input) / 4)
    output_tokens = max(1, len(output or "") / 4)
    return round(input_tokens * 5e-7 + output_tokens * 1.5e-6, 8)


def _blocked(reason: str, policy: str, output: Any = None) -> Dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "policy": policy,
        "output": output,
        "response": output if isinstance(output, str) else json.dumps({
            "status": "blocked",
            "reason": reason,
            "policy": policy,
            "output": output,
        }, indent=2),
    }


class SalesOpsAgent:
    def __init__(self):
        settings.ensure_dirs()
        self.prompt_manager = PromptManager()
        self.input_guardrail = InputGuardrail()
        self.tool_guardrail = ToolGuardrail()
        self.output_guardrail = OutputGuardrail()
        self.logger = StructuredLogger()
        self.tracer = TraceWriter()
        self.hitl = HITLManager()
        self.resolver = AccountResolver()

    def execute_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        approval: Optional[str] = None,
        user_input: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Public tool path — always goes through the tool guardrail and is logged."""
        return self.run(
            user_input or f"tool:{name}",
            approval=approval,
            task_id=task_id,
            forced_tools=[(name, arguments or {})],
        )

    def run(
        self,
        user_input: str,
        approval: Optional[str] = None,
        task_id: Optional[str] = None,
        forced_tools: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
        sandbox_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = time.time()
        run_id = uuid.uuid4().hex[:8]
        tools_called: List[str] = []
        tool_arguments: List[Dict[str, Any]] = []
        tool_outputs: List[Any] = []
        interventions: List[Dict[str, Any]] = []
        errors: List[str] = []
        hitl_decision = "not_required"
        status = "error"
        failure_reason = None
        result: Dict[str, Any] = {
            "status": "error",
            "reason": "uninitialized",
            "policy": None,
            "output": None,
            "response": "",
        }

        set_email_approval(approval)

        try:
            allowed, reason, metadata = self.input_guardrail.check(user_input)
            if not allowed:
                policy = (metadata or {}).get("policy", POLICY_INPUT)
                interventions.append({
                    "layer": "input",
                    "allowed": False,
                    "reason": reason,
                    "policy": policy,
                    "details": metadata or {},
                })
                status = "blocked"
                failure_reason = reason
                result = _blocked(reason, policy)
                result["run_id"] = run_id
                return result

            planned = forced_tools or self._plan(user_input, sandbox_code=sandbox_code)
            email_requested = any(name == "send_email" for name, _ in planned)
            hitl_decision = self.hitl.resolve(approval, email_requested)

            formatted_parts: List[str] = []
            for name, arguments in planned:
                if name == "analyze_data_safely" and sandbox_code and "analysis_code" not in arguments:
                    arguments = {**arguments, "analysis_code": sandbox_code}
                if name == "send_email":
                    arguments = {**arguments, "approval": approval}

                tools_called.append(name)
                tool_arguments.append({"name": name, "arguments": self._safe_args(arguments)})
                tool_result = execute_tool(name, arguments, approval=approval)
                tool_outputs.append(tool_result)

                if tool_result["status"] == "blocked":
                    policy = tool_result.get("policy") or POLICY_INPUT
                    layer = "hitl" if name == "send_email" else "tool"
                    if name == "analyze_data_safely":
                        layer = "sandbox"
                    interventions.append({
                        "layer": layer,
                        "allowed": False,
                        "reason": tool_result.get("reason"),
                        "policy": policy,
                        "details": {"tool": name},
                    })
                    if email_requested:
                        self.hitl.record_decision("send_email", hitl_decision, {"run_id": run_id})
                    status = "blocked"
                    failure_reason = tool_result.get("reason")
                    result = _blocked(tool_result.get("reason") or "blocked", policy)
                    result["run_id"] = run_id
                    result["tools_called"] = tools_called
                    result["hitl_decision"] = hitl_decision
                    return result

                formatted_parts.append(self._format_tool_output(name, tool_result.get("output")))

            if email_requested and hitl_decision == "approved":
                self.hitl.record_decision("send_email", "approved", {"run_id": run_id})

            raw_output = "\n\n".join(part for part in formatted_parts if part)
            allowed, reason, redacted = self.output_guardrail.check(raw_output)
            if not allowed:
                interventions.append({
                    "layer": "output",
                    "allowed": False,
                    "reason": reason,
                    "policy": POLICY_OUTPUT,
                    "details": {},
                })
                status = "blocked"
                failure_reason = reason
                result = _blocked(reason, POLICY_OUTPUT, redacted)
                result["run_id"] = run_id
                result["hitl_decision"] = hitl_decision
                return result

            status = "success"
            result = {
                "status": "success",
                "reason": None,
                "policy": None,
                "output": raw_output,
                "response": raw_output,
                "run_id": run_id,
                "tools_called": tools_called,
                "hitl_decision": hitl_decision,
            }
            return result
        except Exception as exc:
            status = "error"
            failure_reason = str(exc)
            errors.append(str(exc))
            result = {
                "status": "error",
                "reason": failure_reason,
                "policy": None,
                "output": None,
                "response": f"Error processing request: {exc}",
                "run_id": run_id,
            }
            return result
        finally:
            latency = time.time() - start
            output_text = str(result.get("output") or result.get("response") or "")
            self.logger.log_run(
                {
                    "user_input": user_input[:1000],
                    "task_id": task_id,
                    "final_status": status,
                    "tools_called": tools_called,
                    "latency_seconds": latency,
                    "estimated_cost": _estimate_cost(user_input, output_text),
                    "guardrail_interventions": interventions,
                    "hitl_decision": hitl_decision,
                    "failure_reason": failure_reason,
                },
                run_id=run_id,
            )
            self.tracer.save_trace(
                run_id,
                {
                    "input": user_input,
                    "selected_tools": tools_called,
                    "tool_arguments": tool_arguments,
                    "tool_outputs": tool_outputs,
                    "guardrail_decisions": interventions,
                    "hitl_decision": hitl_decision,
                    "final_output": result.get("output") or result.get("response"),
                    "error_messages": errors,
                },
            )
            result.setdefault("run_id", run_id)
            result["latency_seconds"] = latency
            result["estimated_cost"] = _estimate_cost(user_input, output_text)
            result["guardrail_interventions"] = interventions
            result.setdefault("hitl_decision", hitl_decision)
            result.setdefault("tools_called", tools_called)
            set_email_approval(None)

    def _plan(
        self,
        user_input: str,
        sandbox_code: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        text = user_input.lower()

        if "lookup_internal_hr_data" in text:
            return [("lookup_internal_hr_data", {"query": user_input})]
        if "lookup_internal_financial_data" in text:
            query = "CONFIDENTIAL_M_AND_A" if "confidential" in text or "m_and_a" in text else user_input
            return [("lookup_internal_financial_data", {"query": query})]

        if "email" in text and ("send" in text or "draft" in text):
            account = self._extract_account(user_input) or "Acme Corp"
            purpose = "follow-up"
            draft_args = {"account_name_or_id": account, "purpose": purpose}
            draft = execute_tool("draft_email", draft_args)
            send_args = {
                "to": "unknown@example.com",
                "subject": f"Following up on {account}",
                "body": f"Follow-up regarding {account}",
            }
            if draft.get("status") == "success" and isinstance(draft.get("output"), dict):
                payload = draft["output"]
                send_args = {
                    "to": payload.get("to") or send_args["to"],
                    "subject": payload.get("subject") or send_args["subject"],
                    "body": payload.get("body") or send_args["body"],
                }
            return [
                ("draft_email", draft_args),
                ("send_email", send_args),
            ]

        if sandbox_code or "sandbox" in text or ("analyze" in text and "account risk" not in text):
            return [("analyze_data_safely", {
                "analysis_code": sandbox_code or APPROVED_SANDBOX_ANALYSIS,
            })]

        if "ticket" in text or "support" in text:
            return [("summarize_tickets", {})]

        if "risk" in text:
            account = self._extract_account(user_input)
            args = {"account_name_or_id": account} if account else {}
            return [("analyze_account_risk", args)]

        if "pipeline" in text or "opportunit" in text or "deal" in text:
            return [("summarize_pipeline", {}), ("list_open_opportunities", {})]

        account = self._extract_account(user_input)
        if account:
            return [("lookup_account_context", {"account_name_or_id": account})]

        return [("summarize_pipeline", {}), ("summarize_tickets", {})]

    def _extract_account(self, user_input: str) -> Optional[str]:
        lowered = user_input.lower()
        for account in self.resolver.data.accounts:
            name = account.get("name", "")
            if name and name.lower() in lowered:
                return name
            account_id = account.get("account_id", "")
            if account_id and account_id.lower() in lowered:
                return account_id
        return None

    @staticmethod
    def _safe_args(arguments: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(arguments)
        if "analysis_code" in sanitized and isinstance(sanitized["analysis_code"], str):
            sanitized["analysis_code"] = sanitized["analysis_code"][:500]
        sanitized.pop("approval", None)
        return sanitized

    @staticmethod
    def _format_tool_output(name: str, output: Any) -> str:
        if output is None:
            return ""
        if name == "summarize_tickets" and isinstance(output, dict):
            return (
                "Support ticket summary\n"
                f"- Total tickets: {output.get('total', 0)}\n"
                f"- Open tickets: {output.get('open', 0)}\n"
                f"- Critical open: {output.get('critical_open', 0)}\n"
                f"- By severity: {output.get('by_severity', {})}\n"
                f"- By status: {output.get('by_status', {})}"
            )
        if name == "summarize_pipeline" and isinstance(output, dict):
            lines = [
                "Pipeline summary",
                f"- Total opportunities: {output.get('total_opportunities', 0)}",
                f"- Open opportunities: {output.get('open_opportunities', 0)}",
                f"- Total value (USD): {output.get('total_value_usd', 0)}",
                f"- Average deal size (USD): {output.get('average_deal_size_usd', 0)}",
                "- By stage:",
            ]
            for stage, stats in (output.get("by_stage") or {}).items():
                lines.append(f"  - {stage}: {stats.get('count', 0)} deals, {stats.get('amount_usd', 0)} USD")
            return "\n".join(lines)
        if name == "analyze_account_risk" and isinstance(output, dict):
            accounts = output.get("accounts") or []
            if not accounts:
                return "No high-risk accounts were identified."
            lines = [f"Account risk analysis ({output.get('high_risk_count', len(accounts))} accounts):"]
            for row in accounts:
                reasons = ", ".join(row.get("reasons") or [])
                lines.append(f"- {row.get('name')}: health {row.get('health_score')} — {reasons}")
            return "\n".join(lines)
        if name == "analyze_data_safely" and isinstance(output, dict):
            payload = output.get("result") if output.get("result") is not None else output.get("output")
            return f"Sandbox analysis result:\n{json.dumps(payload, indent=2, default=str)}"
        if name == "send_email" and isinstance(output, dict):
            message = output.get("message") or {}
            return (
                "Email sent.\n"
                f"- To: {message.get('to')}\n"
                f"- Subject: {message.get('subject')}\n"
                f"- Status: {output.get('status')}"
            )
        if name == "draft_email" and isinstance(output, dict):
            return (
                "Email drafted (approval required to send).\n"
                f"- To: {output.get('to')}\n"
                f"- Subject: {output.get('subject')}"
            )
        if isinstance(output, (dict, list)):
            return json.dumps(output, indent=2, default=str)
        return str(output)
