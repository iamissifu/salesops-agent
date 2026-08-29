from typing import Any, Dict, List, Optional

from ..config.settings import settings


class DataLoader:
    """Cached CRM data access. Restricted files are never served to the agent tools."""

    def __init__(self):
        self.data_dir = settings.data_dir
        self._cache: Dict[str, Any] = {}

    def load_json(self, filename: str) -> Any:
        if filename in self._cache:
            return self._cache[filename]
        path = self.data_dir / filename
        if not path.exists():
            self._cache[filename] = []
            return []
        import json

        with open(path, "r", encoding="utf-8") as handle:
            self._cache[filename] = json.load(handle)
        return self._cache[filename]

    @property
    def accounts(self) -> List[Dict]:
        return self.load_json("accounts.json")

    @property
    def contacts(self) -> List[Dict]:
        return self.load_json("contacts.json")

    @property
    def opportunities(self) -> List[Dict]:
        return self.load_json("opportunities.json")

    @property
    def activities(self) -> List[Dict]:
        return self.load_json("activities.json")

    @property
    def support_tickets(self) -> List[Dict]:
        return self.load_json("support_tickets.json")

    @property
    def product_usage(self) -> List[Dict]:
        return self.load_json("product_usage.json")

    def get_internal_hr_data(self) -> Optional[Dict]:
        """Restricted dataset — must never be returned through the tool layer."""
        path = self.data_dir / "internal_hr_data.json"
        if path.exists():
            return self.load_json("internal_hr_data.json")
        return None

    def get_internal_financial_data(self) -> Optional[Dict]:
        """Restricted dataset — must never be returned through the tool layer."""
        path = self.data_dir / "internal_financial_data.json"
        if path.exists():
            return self.load_json("internal_financial_data.json")
        return None
