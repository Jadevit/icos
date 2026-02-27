# engine/models/events.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

EventType = Literal[
    "initiative",
    "turn_start",
    "attack_roll",
    "hit",
    "miss",
    "damage",
    "down",
    "combat_end",
]


@dataclass(frozen=True)
class Event:
    type: EventType
    actor: Optional[str] = None
    target: Optional[str] = None
    message: str = ""
    data: Dict[str, object] = field(default_factory=dict)
