import re
from typing import Optional, Tuple

from ..policies import POLICY_OUTPUT

REDACTION_TOKEN = "[REDACTED: restricted_internal_data]"


class OutputGuardrail:
    """Blocks or redacts sensitive content before it reaches the user."""

    def __init__(self):
        self.sensitive_patterns = [
            (r"\$\s*\d[\d,.]*\s*(?:million|billion|[MmBb])?\s*(?:equity\s+)?bonus", "executive_compensation"),
            (r"equity\s+bonus", "executive_compensation"),
            (r"(ceo|cfo|cto|executive).{0,60}(bonus|salary|compensation|equity)", "executive_compensation"),
            (r"(bonus|salary|compensation|equity).{0,40}\$?\s*\d", "executive_compensation"),
            (r"\b(pip|performance improvement plan|employee performance)\b", "employee_performance"),
            (r"\b(terminat(?:e|ed|ion)|fired|layoff|laid\s+off|severance)\b", "termination_or_layoff"),
            (r"\b(m\s*&\s*a|merger|acquisition target|acquire \w+)\b", "mergers_and_acquisitions"),
            (r"confidential.{0,40}(strategy|internal|layoff|m\s*&\s*a)", "confidential_strategy"),
            (
                r"(salary_usd|equity_bonus_usd|performance_status|CONFIDENTIAL_M_AND_A|CONFIDENTIAL_LAYOFF_PLAN)",
                "raw_sensitive_field",
            ),
        ]

    def check(self, output: str) -> Tuple[bool, Optional[str], Optional[str]]:
        if output is None:
            return True, None, output

        text = str(output)
        redacted = text
        matched_category = None

        for pattern, category in self.sensitive_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                redacted = re.sub(pattern, REDACTION_TOKEN, redacted, flags=re.IGNORECASE)
                matched_category = category

        if matched_category:
            if matched_category == "executive_compensation":
                redacted = re.sub(
                    r"\$\s*\d[\d,.]*(?:\s*(?:million|billion|[MmBb]))?",
                    REDACTION_TOKEN,
                    redacted,
                    flags=re.IGNORECASE,
                )
            return False, "restricted_internal_data", redacted

        return True, None, text

    def redact(self, output: str) -> str:
        _, _, redacted = self.check(output)
        return redacted if redacted is not None else REDACTION_TOKEN
