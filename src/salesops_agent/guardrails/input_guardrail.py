import re
from typing import Any, Dict, Optional, Tuple

from ..config.settings import settings
from ..policies import POLICY_INPUT


class InputGuardrail:
    """Blocks restricted or adversarial user input before any tool runs."""

    def __init__(self):
        self.hr_keywords = [kw.lower() for kw in settings.blocked_hr_keywords]
        self.financial_keywords = [kw.lower() for kw in settings.blocked_financial_keywords]
        self.injection_patterns = [
            r"ignore (previous|your|above) (instructions|prompt)",
            r"reveal (hidden|secret|system) (instructions|prompt)",
            r"you are (now|not|no longer)",
            r"forget (previous|all) (instructions|prompt)",
            r"don't (follow|obey|listen to)",
            r"bypass (security|guardrails|restrictions)",
            r"pretend you are",
            r"act as if",
        ]

    def check(self, user_input: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        text = user_input.lower()

        for keyword in self.hr_keywords:
            if self._contains(text, keyword):
                return False, "restricted_internal_data", {
                    "blocked_keyword": keyword,
                    "category": "hr_data",
                    "policy": POLICY_INPUT,
                    "layer": "input",
                }

        for keyword in self.financial_keywords:
            if self._contains(text, keyword):
                return False, "restricted_internal_data", {
                    "blocked_keyword": keyword,
                    "category": "financial_data",
                    "policy": POLICY_INPUT,
                    "layer": "input",
                }

        for pattern in self.injection_patterns:
            if re.search(pattern, text):
                return False, "prompt_injection_detected", {
                    "matched_pattern": pattern,
                    "category": "prompt_injection",
                    "policy": POLICY_INPUT,
                    "layer": "input",
                }

        return True, None, None

    @staticmethod
    def _contains(text: str, keyword: str) -> bool:
        if " " in keyword or "&" in keyword:
            return keyword in text
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
