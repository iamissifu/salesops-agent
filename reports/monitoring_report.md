# SalesOps Agent Monitoring Report

**Generated:** 2026-08-29T17:50:56.914725+00:00

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Runs | 37 |
| Success Rate | 43.2% |
| Failure Rate | 56.8% |
| Policy Blocks | 21 |
| Runtime Failures | 0 |
| Average Latency | 0.013s |
| Total Cost | $0.024066 |
| Average Cost/Run | $0.000650 |

## Tool Usage (from `tools_called`)

| Tool | Calls |
|------|-------|
| draft_email | 10 |
| send_email | 10 |
| analyze_data_safely | 6 |
| summarize_tickets | 5 |
| lookup_internal_hr_data | 5 |
| analyze_account_risk | 2 |
| summarize_pipeline | 2 |
| list_open_opportunities | 2 |
| lookup_internal_financial_data | 2 |

## Guardrail Blocks

| Reason | Count |
|--------|-------|
| restricted_internal_data | 14 |
| hitl_rejected | 5 |
| import of 'os' is not allowed | 2 |

## Human-in-the-Loop

| Metric | Value |
|--------|-------|
| Approvals | 5 |
| Rejections | 5 |
| Total HITL Actions | 10 |

## Failure Breakdown

### Expected policy blocks

| Reason | Count |
|--------|-------|
| restricted_internal_data | 14 |
| hitl_rejected | 5 |
| import of 'os' is not allowed | 2 |

### Unexpected runtime failures

None.

