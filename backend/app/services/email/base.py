"""E-mail provider adapter interface."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EmailMessage:
    to: list[str]
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class EmailResult:
    status: str  # sent | failed | not_configured | logged
    detail: str = ""
    provider: str = ""


class EmailProvider:
    name = "base"

    def configured(self) -> bool:  # pragma: no cover - interface
        return False

    def send(self, message: EmailMessage) -> EmailResult:  # pragma: no cover - interface
        raise NotImplementedError
