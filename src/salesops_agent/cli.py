from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from .agents.salesops_agent import SalesOpsAgent

app = typer.Typer(help="SalesOps Agent — secure sales operations assistant")
console = Console()


def _print_result(result: dict) -> None:
    status = result.get("status")
    body = result.get("response") or result.get("output") or ""
    if status == "blocked":
        details = (
            f"[red]Blocked by security policy[/red]\n\n"
            f"{body}\n\n"
            f"reason: {result.get('reason')}\n"
            f"policy: {result.get('policy')}"
        )
        console.print(Panel(details, title="Access Denied", border_style="red"))
        return
    if status == "error":
        console.print(Panel(str(body), title="Agent Error", border_style="yellow"))
        return
    console.print(Panel(str(body), title="SalesOps Agent Response", border_style="green"))


@app.command()
def ask(
    question: Optional[str] = typer.Argument(None, help="Question to ask the agent"),
    approval: Optional[str] = typer.Option(
        None,
        "--approval",
        help="HITL decision for irreversible actions: approve or reject",
    ),
):
    """Ask a question. Use --approval approve|reject to gate email sending."""
    if not question:
        console.print("[red]Error: please provide a question.[/red]")
        console.print('Usage: salesops-agent ask "How many tickets?"')
        console.print('       salesops-agent ask "Draft and send a follow-up email to Acme Corp" --approval approve')
        raise typer.Exit(code=1)

    if approval is not None and approval not in {"approve", "reject"}:
        console.print("[red]Error: --approval must be 'approve' or 'reject'.[/red]")
        raise typer.Exit(code=1)

    with console.status("[bold cyan]Processing query...[/bold cyan]"):
        result = SalesOpsAgent().run(question, approval=approval)

    _print_result(result)
    console.print(
        f"[dim]run_id={result.get('run_id')}  "
        f"status={result.get('status')}  "
        f"hitl={result.get('hitl_decision')}[/dim]"
    )


@app.command()
def version():
    """Show version information."""
    console.print("[bold]SalesOps Agent[/bold] v0.1.0")
    console.print("Single runtime: src/salesops_agent")
    console.print("  • Input / tool / output guardrails")
    console.print("  • Sandboxed CRM analysis")
    console.print("  • HITL email approval")
    console.print("  • Structured logs and traces")


def main():
    app()


if __name__ == "__main__":
    main()
