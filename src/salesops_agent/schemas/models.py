"""Pydantic schemas for tools, logs, traces, and guardrail decisions."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HITLDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_REQUIRED = "not_required"


class RunStatus(str, Enum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    ERROR = "error"


class GuardrailLayer(str, Enum):
    INPUT = "input"
    TOOL = "tool"
    OUTPUT = "output"
    SANDBOX = "sandbox"
    HITL = "hitl"


class ToolInput(BaseModel):
    """Schema for a proposed tool invocation."""

    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Schema for a tool output, including policy blocks."""

    name: str
    status: str
    output: Optional[Any] = None
    reason: Optional[str] = None
    policy: Optional[str] = None


class ToolCallRecord(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    status: str = "success"


class GuardrailDecision(BaseModel):
    """Record of a single guardrail intervention."""

    layer: GuardrailLayer
    allowed: bool
    reason: Optional[str] = None
    policy: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class BlockedResponse(BaseModel):
    """Standard blocked-response envelope used across all guardrails."""

    status: str = "blocked"
    reason: str
    policy: str
    output: Optional[Any] = None


class LogEntry(BaseModel):
    run_id: str
    timestamp: datetime
    user_input: str
    task_id: Optional[str] = None
    final_status: str
    tools_called: List[str] = Field(default_factory=list)
    latency_seconds: float = 0.0
    estimated_cost: float = 0.0
    guardrail_interventions: List[Dict[str, Any]] = Field(default_factory=list)
    hitl_decision: str = HITLDecision.NOT_REQUIRED.value
    failure_reason: Optional[str] = None


class TraceEntry(BaseModel):
    run_id: str
    input: str
    selected_tools: List[str] = Field(default_factory=list)
    tool_arguments: List[Dict[str, Any]] = Field(default_factory=list)
    tool_outputs: List[Any] = Field(default_factory=list)
    guardrail_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    hitl_decision: str = HITLDecision.NOT_REQUIRED.value
    final_output: Optional[Any] = None
    error_messages: List[str] = Field(default_factory=list)
