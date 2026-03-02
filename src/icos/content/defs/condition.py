from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConditionDefinition:
    id: str
    endpoint: str
    api_index: str
    name: str

    desc: tuple[str, ...] = field(default_factory=tuple)
    url: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)
