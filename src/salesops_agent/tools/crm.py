from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional

from ..data.loader import DataLoader
from ..utils.account_resolver import AccountResolver

data = DataLoader()
resolver = AccountResolver()

OPEN_TICKET_STATUSES = {"open", "in_progress"}
CLOSED_STAGES = {"Closed Won", "Closed Lost"}


def _safe_account(account: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "account_id": account.get("account_id"),
        "name": account.get("name"),
        "industry": account.get("industry"),
        "account_status": account.get("account_status"),
        "health_score": account.get("health_score"),
        "contract_end": account.get("contract_end") or account.get("contract_end_date"),
        "segment": account.get("segment"),
        "region": account.get("region"),
    }


def lookup_account(account_name_or_id: str) -> Dict[str, Any]:
    account = resolver.resolve(account_name_or_id)
    if not account:
        return {"error": f"No account found for {account_name_or_id}"}
    return _safe_account(account)


def lookup_account_context(account_name_or_id: str) -> Dict[str, Any]:
    account = resolver.resolve(account_name_or_id)
    if not account:
        return {"error": f"No account found for {account_name_or_id}"}

    account_id = account.get("account_id")
    return {
        "account": _safe_account(account),
        "contacts": [c for c in data.contacts if c.get("account_id") == account_id],
        "opportunities": [o for o in data.opportunities if o.get("account_id") == account_id],
        "activities": [a for a in data.activities if a.get("account_id") == account_id],
        "support_tickets": [t for t in data.support_tickets if t.get("account_id") == account_id],
        "product_usage": [u for u in data.product_usage if u.get("account_id") == account_id],
    }


def list_open_opportunities(stage: Optional[str] = None) -> List[Dict[str, Any]]:
    results = [o for o in data.opportunities if o.get("stage") not in CLOSED_STAGES]
    if stage:
        results = [o for o in results if o.get("stage", "").lower() == stage.lower()]
    return [
        {
            "opportunity_id": opp.get("opportunity_id") or opp.get("id"),
            "name": opp.get("name"),
            "account_id": opp.get("account_id"),
            "stage": opp.get("stage"),
            "amount_usd": opp.get("amount_usd"),
            "close_date": opp.get("close_date"),
        }
        for opp in results
    ]


def summarize_pipeline() -> Dict[str, Any]:
    by_stage: Dict[str, Dict[str, Any]] = {}
    total_value = 0
    open_count = 0
    for opp in data.opportunities:
        stage = opp.get("stage", "Unknown")
        amount = opp.get("amount_usd", 0) or 0
        by_stage.setdefault(stage, {"count": 0, "amount_usd": 0})
        by_stage[stage]["count"] += 1
        by_stage[stage]["amount_usd"] += amount
        total_value += amount
        if stage not in CLOSED_STAGES:
            open_count += 1
    amounts = [o.get("amount_usd", 0) or 0 for o in data.opportunities]
    average = (sum(amounts) / len(amounts)) if amounts else 0
    return {
        "total_opportunities": len(data.opportunities),
        "open_opportunities": open_count,
        "total_value_usd": total_value,
        "average_deal_size_usd": round(average, 2),
        "by_stage": by_stage,
    }


def summarize_tickets() -> Dict[str, Any]:
    by_severity = Counter()
    by_status = Counter()
    open_tickets = []
    for ticket in data.support_tickets:
        by_severity[ticket.get("severity", "unknown")] += 1
        by_status[ticket.get("status", "unknown")] += 1
        if ticket.get("status") in OPEN_TICKET_STATUSES:
            open_tickets.append(ticket)
    critical_open = sum(
        1
        for ticket in open_tickets
        if ticket.get("severity") == "critical"
    )
    return {
        "total": len(data.support_tickets),
        "open": len(open_tickets),
        "critical_open": critical_open,
        "by_severity": dict(by_severity),
        "by_status": dict(by_status),
    }


def analyze_account_risk(account_name_or_id: Optional[str] = None) -> Dict[str, Any]:
    declining = {
        row.get("account_id")
        for row in data.product_usage
        if row.get("usage_trend") == "down"
    }
    critical_open = {
        ticket.get("account_id")
        for ticket in data.support_tickets
        if ticket.get("severity") == "critical" and ticket.get("status") in OPEN_TICKET_STATUSES
    }

    today = date.today()
    at_risk = []
    for account in data.accounts:
        if account_name_or_id:
            resolved = resolver.resolve(account_name_or_id)
            if not resolved or resolved.get("account_id") != account.get("account_id"):
                continue
        reasons = []
        health = account.get("health_score")
        if isinstance(health, (int, float)) and health < 50:
            reasons.append(f"low health score ({health})")
        if account.get("account_id") in declining:
            reasons.append("declining product usage")
        if account.get("account_id") in critical_open:
            reasons.append("open critical support tickets")
        end = account.get("contract_end") or account.get("contract_end_date")
        if end:
            try:
                end_date = date.fromisoformat(str(end)[:10])
                days = (end_date - today).days
                if 0 <= days <= 90:
                    reasons.append(f"renewal in {days} days")
            except ValueError:
                pass
        if reasons:
            at_risk.append({
                "account_id": account.get("account_id"),
                "name": account.get("name"),
                "health_score": health,
                "reasons": reasons,
            })

    at_risk.sort(key=lambda row: row.get("health_score") or 0)
    return {"high_risk_count": len(at_risk), "accounts": at_risk[:15]}
