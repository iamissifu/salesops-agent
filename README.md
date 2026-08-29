# SalesOps Agent — Production-Ready AgentOps Implementation

A local, reproducible Sales Operations agent with versioned configuration, runtime guardrails, sandboxed analysis, human-in-the-loop email approval, structured logs/traces, and automated evaluation.

There is **one runtime**: `src/salesops_agent/`, invoked only through the `uv` entry points below. The original root-level script lives in `archive/` and is not used.

---

## Project Overview

This project turns the starter SalesOps notebook into an inspectable AgentOps system. The agent answers CRM questions (tickets, pipeline, account risk), can run approved sandbox analysis, and can draft/send follow-up email only after a human approval signal.

Operational controls are enforced in application code:

- input, tool, and output guardrails
- restricted HR / financial-strategy tools that never execute
- sandboxed analysis over approved CRM data only
- HITL gating of `send_email()`
- a log entry and a trace file for every run, including blocks

---

## Prototype Review

The starter notebook (`project_starter.ipynb`) is an in-process demo, not a production agent. Operational gaps identified there:

| Gap in the prototype | Risk |
|---|---|
| CRM tools, email send, and restricted HR/financial lookups live in one notebook with no policy layer | Unbounded tool surface; a model can call `lookup_internal_hr_data` / financial strategy tools |
| No input sanitization | Prompt injection and unrestricted compensation / M&A / layoff questions |
| No output filtering | Sensitive values can be echoed to the user |
| `send_email` writes the outbox immediately | Irreversible customer-facing action without a human |
| No logs, traces, or run IDs | Failures and misuse cannot be reconstructed |
| No evaluation suite | Fixes cannot be regression-tested |
| No sandbox constraints | Any future code-exec path would run against the host |
| Dependencies and prompts are not versioned as project artifacts | Behavior is not reproducible across machines |
| Single shared in-memory state | No user/session isolation |

This repository closes those gaps locally. Suggestions such as Docker, GitHub Actions, or an external observability SaaS are optional stand-out items, not required for the core rubric.

---

## Setup

Prerequisites: Python 3.12+ (see `.python-version`), [`uv`](https://github.com/astral-sh/uv), and the CRM JSON files under `data/`.

```bash
uv sync
```

`uv.lock` is committed. `logs/` and `traces/` are tracked as directories (`.gitkeep`); generated run artifacts are gitignored.

On Git Bash (Windows), add `uv` to `PATH` if `uv` is not found:

```bash
export PATH="/c/Users/sibdo/AppData/Roaming/Python/Python313/Scripts:$PATH"
```

---

## Run Commands

Documented agent entry point:

```bash
uv run salesops-agent ask "How many open tickets?"
```

That command prints the agent answer to the terminal and writes a new `logs/runs.jsonl` line plus `traces/<run_id>.json`.

```bash
uv run salesops-agent ask "Which accounts are at risk and why?"
uv run salesops-agent ask "What is the pipeline value by stage?"
uv run salesops-agent ask "What is the CEO's bonus?"   # blocked by input guardrail

uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval approve
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval reject
```

---

## Evaluation Commands

```bash
uv run evaluate
```

The suite actually executes the agent and tools (10 live tasks). It writes `reports/evaluation_report.{md,csv,json}` and exits nonzero if any task fails.

---

## Monitoring Report Commands

```bash
uv run generate-monitoring-report
```

Writes `reports/monitoring_report.{md,json,csv}` from aggregated `logs/runs.jsonl` fields.

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

The runtime is deterministic and does not require an OpenAI key. LangChain is not on the execution or evaluation path.

```
src/salesops_agent/
├── agents/salesops_agent.py   # orchestrator only
├── schemas/                   # tool / log / trace / guardrail contracts
├── config/settings.py
├── prompts/versioned/         # YAML system prompt
├── guardrails/
├── tools/
├── hitl/manager.py
├── logging/structured_logger.py
├── evaluation/runner.py
└── monitoring/report.py
```

---

## Versioned Components

These live **outside** the agent execution module:

| Component | Location |
|---|---|
| Dependency lock | `uv.lock`, `.python-version`, `pyproject.toml` |
| Settings / policy keywords / sandbox allowlist | `src/salesops_agent/config/settings.py` |
| System prompt | `src/salesops_agent/prompts/versioned/system_prompt_v1.yaml` |
| JSON Schema + Pydantic models | `src/salesops_agent/schemas/` |
| Named policies | `src/salesops_agent/policies.py` |
| CRM and restricted datasets | `data/*.json` |

Bump the prompt file (`system_prompt_v1.yaml` → `v2`) and `PromptManager.current_version` to change instructions without editing the orchestrator.

---

## Guardrail Design

Enforcement is in application modules (`guardrails/` + `tools.execute_tool`), not a prompt asking the model to behave.

Blocked responses use:

```json
{
  "status": "blocked",
  "reason": "restricted_internal_data",
  "policy": "salesops_data_access_policy",
  "output": null
}
```

**Input** (`salesops_input_policy`) runs first. It blocks executive compensation, M&A, layoffs, employee termination, and prompt-injection patterns.

**Tool** (`salesops_data_access_policy` / `salesops_email_approval_policy`) intercepts every proposed call. `lookup_internal_hr_data` and `lookup_internal_financial_data` are blocked before any file read. `send_email()` is blocked unless `--approval approve`.

**Output** (`salesops_output_policy`) inspects the final response and blocks or redacts executive compensation, employee performance, M&A, and layoff content (`[REDACTED: restricted_internal_data]`).

Every intervention is written to `guardrail_interventions` in the run log.

---

## Sandboxed Execution

`analyze_data_safely` is the code-execution / data-analysis tool.

**Capabilities.** Runs approved Python over CRM context only: accounts, opportunities, contacts, activities, tickets, product usage. Typical analyses: pipeline value by stage, open opportunity counts, average deal size, high-risk renewals, ticket severity, health score vs. renewal date.

**Restrictions.**

- AST + restricted builtins — not unrestricted `eval` / `exec` against the host
- Import allowlist (`statistics`, `math`, `collections`, `datetime`, `json`, `pandas` if installed); `os`, `subprocess`, `socket`, `requests`, and similar modules are denied
- Execution timeout (`sandbox_timeout_seconds`, default 5s)
- No network access
- HR and confidential financial files are never loaded into the sandbox

**Remaining limitations.** This is process-level isolation, not a container or gVisor. A determined payload that escaped the AST allowlist would still share the host Python process. Production should move execution into OS-level isolation.

---

## Human-in-the-Loop Workflow

Sending email is the high-risk action. The workflow does not send until an approval signal is present. The CLI flag is `--approval approve` or `--approval reject`.

```bash
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval approve
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval reject
```

| Signal | Behavior | `hitl_decision` |
|---|---|---|
| `--approval approve` | `send_email()` completes; `data/email_outbox.json` is updated | `approved` |
| `--approval reject` | Send does not complete | `rejected` |
| omitted on an email request | Treated as not approved; send is blocked | `rejected` |
| omitted on a non-email request | No HITL gate | `not_required` |

The gate lives in `ToolGuardrail.check_tool_call()` and again inside `send_email()`. There is no tool path that writes the outbox without approval. The decision is stored in both `logs/runs.jsonl` and `traces/<run_id>.json`.

---

## Logging and Tracing

**Log location:** `logs/runs.jsonl` (one JSON object per line).

**Trace location:** `traces/<run_id>.json`.

Every invocation — success, block, or error — writes both, from a `finally` block.

Log fields: `run_id`, `timestamp`, `user_input`, `task_id`, `final_status`, `tools_called`, `latency_seconds`, `estimated_cost`, `guardrail_interventions`, `hitl_decision`, `failure_reason`.

Trace fields: `run_id`, `input`, `selected_tools`, `tool_arguments`, `tool_outputs` (redacted where needed), `guardrail_decisions`, `hitl_decision`, `final_output`, `error_messages`.

**Redaction.** Sensitive raw HR and financial-strategy values are replaced with `[REDACTED: restricted_internal_data]`, not omitted.

```bash
uv run python -c "from pathlib import Path; print([l for l in Path('logs/runs.jsonl').read_text().splitlines() if 'blocked' in l][-1])"
uv run python -m json.tool traces/<run_id>.json
```

---

## Monitoring Report

Generate:

```bash
uv run generate-monitoring-report
```

**Output location:** `reports/monitoring_report.md`, `reports/monitoring_report.json`, `reports/monitoring_report.csv`.

**Metrics** (aggregates from real log fields, not a per-run dump): total runs, success rate, failure rate, average latency, total estimated cost, average cost per run, tool call counts, guardrail block counts, HITL approvals, HITL rejections, and common failure reasons grouped as expected policy blocks vs. unexpected runtime failures.

---

## Known Limitations

- Guardrails are keyword/regex plus an application policy layer. They are auditable but can false-positive or miss paraphrases.
- The sandbox is not containerized; absence of host/`os` access is enforced in-process.
- Email is written to a local outbox JSON file, not SMTP.
- Single-user, local files only — no multi-tenant auth or distributed tracing.
- The agent planner is deterministic (reproducible, no API key). It does not do open-ended LLM tool-calling.

---

## Production Hardening Recommendations

| Area | Recommendation |
|---|---|
| Security | OAuth2/JWT with RBAC; secrets in a vault; encrypt logs/traces at rest |
| Guardrails | Replace keyword filters with a dedicated classifier; red-team prompt-injection paraphrases |
| Sandboxing | OS-level isolation (containers / gVisor / Firecracker) for any code execution |
| Observability | OpenTelemetry + an external backend (LangSmith, Langfuse, or MLflow) |
| Infrastructure | Multi-stage Dockerfile; CI evaluation on every push |
| Data | PostgreSQL (or similar) with backups and a retention policy |
| Isolation | Explicit user / session / thread / run IDs so memory cannot cross users |

---

## Project Structure

```
.
├── src/salesops_agent/
├── data/
├── logs/
├── traces/
├── reports/
├── archive/                     # unused legacy script
├── pyproject.toml
├── uv.lock
├── .python-version
├── GITLOG.txt
└── README.md
```

---

## License

MIT

Built for the Udacity AgentOps project track, using mock CRM data.
