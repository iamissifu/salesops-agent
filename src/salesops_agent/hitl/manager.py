import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..config.settings import settings


class HITLManager:
    """Records human approval decisions that gate irreversible actions."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or settings.data_dir / "approvals.json"
        self._history: list = []
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                self._history = data.get("history", [])
        else:
            self._history = []

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as handle:
            json.dump({"history": self._history}, handle, indent=2)

    def record_decision(
        self,
        action: str,
        decision: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = {
            "action": action,
            "decision": decision,
            "details": details or {},
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(record)
        self._save()
        return record

    def resolve(self, approval: Optional[str], email_requested: bool) -> str:
        if not email_requested:
            return "not_required"
        if approval == "approve":
            return "approved"
        return "rejected"
