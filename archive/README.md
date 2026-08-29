# Archived implementations

`salesops_agent_legacy.py` is the original root-level deterministic script. It is **not** used by any entry point.

The only supported runtime is `src/salesops_agent/`, invoked via:

```bash
uv run salesops-agent ask "..."
uv run evaluate
uv run generate-monitoring-report
```
