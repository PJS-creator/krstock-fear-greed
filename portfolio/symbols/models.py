from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolCandidate:
    market: str
    ticker: str
    display_name: str
    currency: str


@dataclass(frozen=True)
class SymbolResolution:
    raw_input: str
    market: str = ""
    ticker: str = ""
    display_name: str = ""
    currency: str = ""
    confidence: float = 0.0
    candidates: list[SymbolCandidate] = field(default_factory=list)
    status: str = "unresolved"
    message: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved"


@dataclass(frozen=True)
class InputPreviewResult:
    rows: list[dict[str, object]]
    errors: list[str]
    summary: dict[str, int]
