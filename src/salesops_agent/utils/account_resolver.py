import re
import difflib
from typing import Dict, Any, Optional, List
from ..data.loader import DataLoader

class AccountResolver:
    def __init__(self):
        self.data = DataLoader()
        
    def normalize_text(self, value: str) -> str:
        """Normalize names for fuzzy matching"""
        value = value.lower().strip()
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        value = re.sub(r"\b(incorporated|inc|corp|corporation|ltd|limited|llc|co|company)\b", "", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value
    
    def find_by_id(self, account_id: str) -> Optional[Dict[str, Any]]:
        account_id_norm = account_id.strip().lower()
        return next(
            (a for a in self.data.accounts if a.get('account_id', '').lower() == account_id_norm),
            None
        )
    
    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        query = self.normalize_text(name)
        
        # Exact match
        for account in self.data.accounts:
            if query == self.normalize_text(account.get('name', '')):
                return account
        
        # Partial match
        for account in self.data.accounts:
            account_name = self.normalize_text(account.get('name', ''))
            if query and (query in account_name or account_name in query):
                return account
        
        # Fuzzy match
        normalized_names = {self.normalize_text(a.get('name', '')): a for a in self.data.accounts}
        matches = difflib.get_close_matches(query, normalized_names.keys(), n=1, cutoff=0.82)
        if matches:
            return normalized_names[matches[0]]
        
        return None
    
    def resolve(self, account_name_or_id: str) -> Optional[Dict[str, Any]]:
        return self.find_by_id(account_name_or_id) or self.find_by_name(account_name_or_id)