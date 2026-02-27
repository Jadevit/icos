# engine/models/events.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Literal, Optional

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
    """
    Immutable record of a factual outcome produced by the engine.
    This is what you log/stream to UI/AI later.
    """
    type: EventType
    actor: Optional[str] = None
    target: Optional[str] = None
    message: str = ""
    data: Mapping[str, object] = field(default_factory=dict)