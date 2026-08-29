import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..config.settings import settings
from ..guardrails.output_guardrail import REDACTION_TOKEN, OutputGuardrail

SENSITIVE_FIELD_NAMES = {
    "salary",
    "salary_usd",
    "bonus",
    "equity",
    "equity_bonus_usd",
    "compensation",
    "performance_status",
    "confidential_strategy",
    "confidential_m_and_a",
    "confidential_layoff_plan",
    "planned_reduction",
}


class StructuredLogger:
    def __init__(self):
        self.log_dir = settings.logs_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "runs.jsonl"

    def log_run(self, run_data: Dict[str, Any], run_id: str | None = None) -> str:
        run_id = run_id or uuid.uuid4().hex[:8]
        log_entry = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_input": run_data.get("user_input", ""),
            "task_id": run_data.get("task_id"),
            "final_status": run_data.get("final_status", "error"),
            "tools_called": run_data.get("tools_called", []),
            "latency_seconds": run_data.get("latency_seconds", 0.0),
            "estimated_cost": run_data.get("estimated_cost", 0.0),
            "guardrail_interventions": run_data.get("guardrail_interventions", []),
            "hitl_decision": run_data.get("hitl_decision", "not_required"),
            "failure_reason": run_data.get("failure_reason"),
        }
        with open(self.log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(log_entry) + "\n")
        return run_id


class TraceWriter:
    def __init__(self):
        self.trace_dir = settings.traces_dir
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._output_guardrail = OutputGuardrail()

    def save_trace(self, run_id: str, trace_data: Dict[str, Any]) -> None:
        payload = {
            "run_id": run_id,
            "input": trace_data.get("input", ""),
            "selected_tools": trace_data.get("selected_tools", []),
            "tool_arguments": self._redact(trace_data.get("tool_arguments", [])),
            "tool_outputs": self._redact(trace_data.get("tool_outputs", [])),
            "guardrail_decisions": trace_data.get("guardrail_decisions", []),
            "hitl_decision": trace_data.get("hitl_decision", "not_required"),
            "final_output": self._redact(trace_data.get("final_output")),
            "error_messages": trace_data.get("error_messages", []),
        }
        with open(self.trace_dir / f"{run_id}.json", "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if self._is_sensitive_key(key):
                    redacted[key] = REDACTION_TOKEN
                else:
                    redacted[key] = self._redact(item)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, str):
            allowed, _, redacted = self._output_guardrail.check(value)
            if not allowed:
                return redacted
            if self._looks_restricted(value):
                return REDACTION_TOKEN
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        normalized = str(key).lower()
        return any(pattern in normalized for pattern in SENSITIVE_FIELD_NAMES)

    @staticmethod
    def _looks_restricted(text: str) -> bool:
        lowered = text.lower()
        markers = (
            "salary_usd",
            "equity_bonus_usd",
            "confidential_m_and_a",
            "confidential_layoff",
            "performance_status",
        )
        return any(marker in lowered for marker in markers)
