# SalesOps Agent Monitoring Report

**Generated:** 2026-08-29T16:09:11.827793+00:00

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Runs | 5 |
| Success Rate | 40.0% |
| Failure Rate | 60.0% |
| Policy Blocks | 3 |
| Runtime Failures | 0 |
| Average Latency | 0.011s |
| Total Cost | $0.000321 |
| Average Cost/Run | $0.000064 |

## Tool Usage (from `tools_called`)

| Tool | Calls |
|------|-------|
| draft_email | 2 |
| send_email | 2 |
| summarize_tickets | 1 |
| lookup_internal_hr_data | 1 |

## Guardrail Blocks

| Reason | Count |
|--------|-------|
| restricted_internal_data | 2 |
| hitl_rejected | 1 |

## Human-in-the-Loop

| Metric | Value |
|--------|-------|
| Approvals | 1 |
| Rejections | 1 |
| Total HITL Actions | 2 |

## Failure Breakdown

### Expected policy blocks

| Reason | Count |
|--------|-------|
| restricted_internal_data | 2 |
| hitl_rejected | 1 |

### Unexpected runtime failures

None.

