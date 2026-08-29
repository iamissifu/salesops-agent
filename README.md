# SalesOps Agent — Production-Ready AgentOps Implementation

A local, reproducible Sales Operations agent with versioned configuration, runtime guardrails, sandboxed analysis, human-in-the-loop email approval, structured logs/traces, and automated evaluation.

There is **one runtime**: `src/salesops_agent/`, invoked only through the `uv` entry points below. The original root-level script lives in `archive/` and is not used.

---

## Why this project exists

A demo SalesOps agent that can read CRM data and draft emails is not enough. This system treats AgentOps as a security problem:

| Prototype failure | Control in this repo |
|---|---|
| Unrestricted HR / financial-strategy tools | Tool guardrail blocks `lookup_internal_hr_data` and `lookup_internal_financial_data` in application code before execution |
| Prompt injection / restricted questions | Input guardrail blocks HR, M&A, compensation, and injection patterns |
| Sensitive data in model output | Output guardrail blocks/redacts compensation, performance/termination, M&A, layoffs, and raw restricted fields |
| Email send without review | `send_email()` requires `--approval approve`; reject or missing approval cannot send, even if the tool is called directly |
| Arbitrary code execution | Sandbox allowlists safe modules, denies `eval`/`exec`/`os`/`network`, times out, and never loads HR/financial files |
| Invisible failures | Every run — including blocked ones — writes `logs/runs.jsonl` and `traces/<run_id>.json` |

---

## Architecture

```
User input
   │
   ▼
Input Guardrail  ──► blocked? → {status, reason, policy, output} + log + trace
   │ allowed
   ▼
Deterministic planner (CRM / risk / pipeline / sandbox / email / named tools)
   │
   ▼
Tool Guardrail.check_tool_call()  ── every proposed tool, including direct calls
   │
   ├─► CRM tools (accounts, tickets, pipeline, risk)
   ├─► Sandbox (approved analysis only)
   └─► send_email() ── HITL: approve → outbox; reject → blocked
   │
   ▼
Output Guardrail  ──► block / redact restricted content
   │
   ▼
finally: logs/runs.jsonl + traces/<run_id>.json
```

The agent is deterministic and does **not** require an OpenAI key. LangChain is not on the runtime or evaluation path, so `uv sync` and `uv run evaluate` stay reproducible.

```
src/salesops_agent/
├── agents/salesops_agent.py   # orchestrator (plan → guarded tools → output filter)
├── schemas/                   # Pydantic models + JSON Schema for tools/logs/traces/guardrails
├── config/settings.py         # model, paths, sandbox allowlist, blocked keywords
├── prompts/                   # versioned system prompt (YAML)
├── guardrails/
│   ├── input_guardrail.py
│   ├── tool_guardrail.py
│   └── output_guardrail.py
├── tools/                     # CRM, sandbox, email, restricted HR/financial tools
├── hitl/manager.py            # approval decisions written to audit history
├── logging/structured_logger.py
├── evaluation/runner.py       # 10 live tests → reports/evaluation_report.{md,csv,json}
└── monitoring/report.py       # aggregates real log fields → reports/monitoring_report.*
```

---

## Guardrails

Blocked responses always use the same envelope:

```json
{
  "status": "blocked",
  "reason": "restricted_internal_data",
  "policy": "salesops_data_access_policy",
  "output": null
}
```

### Input guardrail (`salesops_input_policy`)

Blocks compensation/HR terms, M&A/confidential-strategy terms, and prompt-injection patterns **before** any tool runs.

### Tool guardrail (`salesops_data_access_policy` / `salesops_email_approval_policy`)

`ToolGuardrail.check_tool_call()` is the only path into tool execution (`tools.execute_tool`). Restricted tools return `reason: restricted_internal_data` and never read `data/internal_hr_data.json` or `data/internal_financial_data.json`. `send_email()` re-checks approval inside the tool so it cannot be bypassed by calling the function directly.

### Output guardrail (`salesops_output_policy`)

Catches executive compensation, employee performance/termination, M&A, layoffs, confidential internal strategy, and raw sensitive field names. Matches are replaced with `[REDACTED: restricted_internal_data]`. Ordinary CRM pipeline amounts are not treated as compensation.

Every intervention is appended to `guardrail_interventions` in `logs/runs.jsonl`.

---

## Sandboxed code execution

`analyze_data_safely` runs approved Python over CRM data only (accounts, opportunities, tickets, usage). It can compute pipeline value by stage, open opportunity counts, average deal size, high-risk renewals, ticket severity, and health vs. renewal date.

Denied:

- `eval` / `exec` / `__import__` of non-allowlisted modules
- `import os`, `subprocess`, `socket`, `requests`, and other host/network modules
- reading HR or financial data sources
- runs longer than `sandbox_timeout_seconds` (default 5s)

Allowlisted modules include `statistics`, `math`, `collections`, `datetime`, `json`, and `pandas` (if installed). Execution uses a restricted builtin set after AST validation — not unrestricted `eval`/`exec` against the host.

---

## Human-in-the-loop email approval

```bash
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval approve
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval reject
```

| Flag | Effect | `hitl_decision` |
|---|---|---|
| `--approval approve` | Draft + send; `data/email_outbox.json` updated | `approved` |
| `--approval reject` | Draft may run; send is blocked; outbox unchanged | `rejected` |
| omitted (no email) | N/A | `not_required` |
| omitted (email requested) | Send blocked (`hitl_approval_required`) | `rejected` |

The decision is written to both `logs/runs.jsonl` and `traces/<run_id>.json`.

---

## Logging and traces

**Every** run, including guardrail blocks, writes both artifacts in a `finally` block.

`logs/runs.jsonl` fields: `run_id`, `timestamp`, `user_input`, `task_id`, `final_status`, `tools_called`, `latency_seconds`, `estimated_cost`, `guardrail_interventions`, `hitl_decision`, `failure_reason`.

`traces/<run_id>.json` fields: `run_id`, `input`, `selected_tools`, `tool_arguments`, `tool_outputs`, `guardrail_decisions`, `hitl_decision`, `final_output`, `error_messages`.

Sensitive raw values are replaced with `[REDACTED: restricted_internal_data]`, not silently dropped.

---

## Evaluation and monitoring

```bash
uv run evaluate
uv run generate-monitoring-report
```

`evaluate` **executes** the agent and tools for 10 cases (no hardcoded `success: true`):

1. Normal SalesOps question — open tickets
2. Account-risk reasoning
3. Pipeline / opportunity reasoning
4. Restricted input blocked by the input guardrail
5. Forbidden HR/financial tool call blocked
6. Sensitive output blocked/redacted
7. Sandbox-allowed CRM analysis succeeds
8. Sandbox-denied unsafe execution (`import os`, etc.)
9. Approved email send completes
10. Rejected email send does not complete

The process exits **nonzero** if any task fails. Reports: `reports/evaluation_report.{md,csv,json}`.

`generate-monitoring-report` aggregates **real** `tools_called` and `hitl_decision` fields from the log. It writes `reports/monitoring_report.{md,json,csv}` with total runs, success/failure rates, latency, cost, per-tool counts, guardrail blocks, HITL approve/reject counts, and a breakdown of expected policy blocks vs. unexpected runtime failures.

---

## Getting started

### Prerequisites

- Python 3.12+ (see `.python-version`)
- [`uv`](https://github.com/astral-sh/uv)
- CRM files in `data/` (`accounts.json`, `opportunities.json`, `support_tickets.json`, `product_usage.json`, …)

### Install

```bash
uv sync
```

`uv.lock` is committed. `logs/` and `traces/` are tracked as directories (`.gitkeep`); generated `*.jsonl` / `*.json` run artifacts are ignored.

### Run

```bash
uv run salesops-agent ask "How many open tickets?"
uv run salesops-agent ask "Which accounts are at risk and why?"
uv run salesops-agent ask "What is the pipeline value by stage?"
uv run salesops-agent ask "What is the CEO's bonus?"   # blocked

uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval approve
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval reject
```

### Inspect a run

```bash
# latest blocked log line
# (use Select-String on Windows PowerShell)
uv run python -c "from pathlib import Path; print([l for l in Path('logs/runs.jsonl').read_text().splitlines() if 'blocked' in l][-1])"

# full trace
uv run python -m json.tool traces/<run_id>.json
```

---

## Project structure

```
.
├── src/salesops_agent/          # only supported implementation
│   ├── schemas/                 # JSON Schema + Pydantic models
│   ├── agents/
│   ├── guardrails/
│   ├── tools/
│   ├── hitl/
│   ├── logging/
│   ├── evaluation/
│   └── monitoring/
├── data/                        # mock CRM + restricted internal files (never served)
├── logs/                        # runs.jsonl (generated)
├── traces/                      # <run_id>.json (generated)
├── reports/                     # evaluation + monitoring reports
├── archive/                     # unused legacy script (not an entry point)
├── pyproject.toml
├── uv.lock
├── .python-version
└── README.md
```

---

## Production hardening (next)

- Replace keyword/regex guards with a dedicated classifier and red-team the input path for paraphrase/encoding evasion
- Put code execution in OS-level isolation (containers / gVisor), not only an AST allowlist
- OpenTelemetry traces, secret managers, and RBAC if this leaves the local demo
- PostgreSQL (or similar) instead of JSON files, with an explicit retention policy

---

## License

MIT

Built for the Udacity AgentOps project track, using mock CRM data.
