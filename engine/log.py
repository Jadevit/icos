# engine/log.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List

from .models import Event


@dataclass
class EventLog:
    events: List[Event] = field(default_factory=list)

    def add(self, event: Event) -> None:
        self.events.append(event)

    def extend(self, events: List[Event]) -> None:
        self.events.extend(events)

    def to_dicts(self) -> List[dict]:
        return [asdict(e) for e in self.events]

    def pretty(self) -> str:
        return "\n".join(f"[{e.type}] {e.message}" for e in self.events)
