"""Additional local guardrails; not a DLP system or a privacy classifier."""
import re
import unicodedata

from aegis.policy import DataClass
from aegis.security.gateway import GatewayDenied

# Intentionally conservative: even examples containing these patterns can be denied.
BLOCKED_PATTERNS = (
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
    r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)",
    r"(?<!\d)(?:\+1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\d)",
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----",
    r"\b(?:AIza[\w-]{30,}|sk-[\w-]{16,}|gh[pousr]_[\w]{20,}|github_pat_[\w_]{20,})\b",
    r"\b(?:password|passwd|api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*\S+",
    r"\bAuthorization\s*:\s*Bearer\s+\S+",
)


def require_reviewed_content(parts: list[str], classification: DataClass, approved: bool):
    if approved is not True or classification not in {DataClass.PUBLIC, DataClass.SYNTHETIC}:
        raise GatewayDenied("Public or synthetic content review required")

    for part in parts:
        normalized = unicodedata.normalize("NFKC", part)
        if any(unicodedata.category(c) == "Cf" for c in normalized):
            raise GatewayDenied("Content requires offline review")
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in BLOCKED_PATTERNS):
            raise GatewayDenied("Content requires offline review")
