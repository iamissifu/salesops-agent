import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..config.settings import settings


def _load_runs(logs_path: Path) -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    if not logs_path.exists():
        return runs
    with open(logs_path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return runs


def _status(run: Dict[str, Any]) -> str:
    raw = str(run.get("final_status") or run.get("status") or "").lower()
    if raw in {"success", "completed"}:
        return "success"
    if raw == "blocked":
        return "blocked"
    if raw == "error":
        return "error"
    return raw or "unknown"


def _latency(run: Dict[str, Any]) -> float:
    value = run.get("latency_seconds", run.get("latency", 0)) or 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cost(run: Dict[str, Any]) -> float:
    value = run.get("estimated_cost", 0) or 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tools(run: Dict[str, Any]) -> List[str]:
    tools = run.get("tools_called") or []
    if isinstance(tools, list):
        return [str(tool) for tool in tools]
    return []


def _interventions(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = run.get("guardrail_interventions") or []
    if not isinstance(raw, list):
        return []
    normalized = []
    for item in raw:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"reason": str(item), "layer": "unknown"})
    return normalized


def generate_report() -> None:
    logs_path = settings.logs_dir / "runs.jsonl"
    runs = _load_runs(logs_path)
    if not runs:
        print("No logs found. Run some queries first.")
        print('Example: uv run salesops-agent ask "How many open tickets?"')
        return

    total_runs = len(runs)
    success_runs = sum(1 for run in runs if _status(run) == "success")
    policy_blocks = sum(1 for run in runs if _status(run) == "blocked")
    runtime_failures = sum(1 for run in runs if _status(run) == "error")
    failed_runs = policy_blocks + runtime_failures

    latencies = [_latency(run) for run in runs]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    total_cost = sum(_cost(run) for run in runs)
    avg_cost = total_cost / total_runs if total_runs else 0

    tool_counts: Counter[str] = Counter()
    for run in runs:
        for tool in _tools(run):
            tool_counts[tool] += 1

    guardrail_counts: Counter[str] = Counter()
    policy_reasons: Counter[str] = Counter()
    runtime_reasons: Counter[str] = Counter()
    for run in runs:
        for intervention in _interventions(run):
            key = intervention.get("reason") or intervention.get("layer") or "unknown"
            guardrail_counts[str(key)] += 1
        status = _status(run)
        reason = run.get("failure_reason") or "unspecified"
        if status == "blocked":
            policy_reasons[str(reason)] += 1
        elif status == "error":
            runtime_reasons[str(reason)] += 1

    hitl_approvals = sum(1 for run in runs if run.get("hitl_decision") == "approved")
    hitl_rejections = sum(1 for run in runs if run.get("hitl_decision") == "rejected")

    report_dir = settings.reports_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    report_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runs": total_runs,
        "successful_runs": success_runs,
        "failed_runs": failed_runs,
        "policy_blocks": policy_blocks,
        "runtime_failures": runtime_failures,
        "success_rate": success_runs / total_runs if total_runs else 0,
        "failure_rate": failed_runs / total_runs if total_runs else 0,
        "average_latency_seconds": avg_latency,
        "total_cost_usd": total_cost,
        "average_cost_per_run_usd": avg_cost,
        "tool_usage": dict(tool_counts),
        "guardrail_blocks": dict(guardrail_counts),
        "hitl_approvals": hitl_approvals,
        "hitl_rejections": hitl_rejections,
        "total_hitl_actions": hitl_approvals + hitl_rejections,
        "common_failure_reasons": {
            "policy_blocks": dict(policy_reasons.most_common(10)),
            "runtime_failures": dict(runtime_reasons.most_common(10)),
        },
    }

    json_path = report_dir / "monitoring_report.json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report_data, handle, indent=2)

    csv_path = report_dir / "monitoring_report.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["total_runs", total_runs])
        writer.writerow(["successful_runs", success_runs])
        writer.writerow(["failed_runs", failed_runs])
        writer.writerow(["policy_blocks", policy_blocks])
        writer.writerow(["runtime_failures", runtime_failures])
        writer.writerow(["success_rate", f"{report_data['success_rate']:.4f}"])
        writer.writerow(["failure_rate", f"{report_data['failure_rate']:.4f}"])
        writer.writerow(["average_latency_seconds", f"{avg_latency:.6f}"])
        writer.writerow(["total_cost_usd", f"{total_cost:.8f}"])
        writer.writerow(["average_cost_per_run_usd", f"{avg_cost:.8f}"])
        writer.writerow(["hitl_approvals", hitl_approvals])
        writer.writerow(["hitl_rejections", hitl_rejections])
        for tool, count in tool_counts.most_common():
            writer.writerow([f"tool.{tool}", count])
        for reason, count in policy_reasons.most_common():
            writer.writerow([f"failure.policy.{reason}", count])
        for reason, count in runtime_reasons.most_common():
            writer.writerow([f"failure.runtime.{reason}", count])

    md_path = report_dir / "monitoring_report.md"
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# SalesOps Agent Monitoring Report\n\n")
        handle.write(f"**Generated:** {report_data['generated_at']}\n\n")
        handle.write("## Executive Summary\n\n")
        handle.write("| Metric | Value |\n|--------|-------|\n")
        handle.write(f"| Total Runs | {total_runs} |\n")
        handle.write(f"| Success Rate | {report_data['success_rate'] * 100:.1f}% |\n")
        handle.write(f"| Failure Rate | {report_data['failure_rate'] * 100:.1f}% |\n")
        handle.write(f"| Policy Blocks | {policy_blocks} |\n")
        handle.write(f"| Runtime Failures | {runtime_failures} |\n")
        handle.write(f"| Average Latency | {avg_latency:.3f}s |\n")
        handle.write(f"| Total Cost | ${total_cost:.6f} |\n")
        handle.write(f"| Average Cost/Run | ${avg_cost:.6f} |\n\n")

        handle.write("## Tool Usage (from `tools_called`)\n\n")
        if tool_counts:
            handle.write("| Tool | Calls |\n|------|-------|\n")
            for tool, count in tool_counts.most_common():
                handle.write(f"| {tool} | {count} |\n")
            handle.write("\n")
        else:
            handle.write("No tool-call events recorded.\n\n")

        handle.write("## Guardrail Blocks\n\n")
        if guardrail_counts:
            handle.write("| Reason | Count |\n|--------|-------|\n")
            for reason, count in guardrail_counts.most_common():
                handle.write(f"| {reason} | {count} |\n")
            handle.write("\n")
        else:
            handle.write("No guardrail interventions recorded.\n\n")

        handle.write("## Human-in-the-Loop\n\n")
        handle.write("| Metric | Value |\n|--------|-------|\n")
        handle.write(f"| Approvals | {hitl_approvals} |\n")
        handle.write(f"| Rejections | {hitl_rejections} |\n")
        handle.write(f"| Total HITL Actions | {hitl_approvals + hitl_rejections} |\n\n")

        handle.write("## Failure Breakdown\n\n")
        handle.write("### Expected policy blocks\n\n")
        if policy_reasons:
            handle.write("| Reason | Count |\n|--------|-------|\n")
            for reason, count in policy_reasons.most_common(10):
                handle.write(f"| {reason} | {count} |\n")
            handle.write("\n")
        else:
            handle.write("None.\n\n")
        handle.write("### Unexpected runtime failures\n\n")
        if runtime_reasons:
            handle.write("| Reason | Count |\n|--------|-------|\n")
            for reason, count in runtime_reasons.most_common(10):
                handle.write(f"| {reason} | {count} |\n")
            handle.write("\n")
        else:
            handle.write("None.\n\n")

    print(f"\nMonitoring report generated: {md_path}")
    print(f"   JSON: {csv_path.parent / 'monitoring_report.json'}")
    print(f"   CSV:  {csv_path}")


if __name__ == "__main__":
    generate_report()
