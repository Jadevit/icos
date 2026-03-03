from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

EVENT_SCHEMA_V1 = "icos.event.v1"


# --- Canonical engine lifecycle events ------------------------------------
ENCOUNTER_STARTED = "encounter.started"
ENCOUNTER_ENDED = "encounter.ended"
ROUND_STARTED = "round.started"
ROUND_ENDED = "round.ended"
TURN_STARTED = "turn.started"
TURN_ENDED = "turn.ended"
TURN_SKIPPED = "turn.skipped"

ACTION_REQUESTED = "action.requested"   # controller produced an ActionRequest
ACTION_VALIDATED = "action.validated"   # loop accepted/normalized it
ACTION_RESOLVED = "action.resolved"     # loop produced outcomes/events
ACTION_APPLIED = "action.applied"       # loop mutated state (if it distinguishes resolve/apply)


@dataclass(frozen=True)
class Event:
    """
    Immutable record of a factual occurrence during an encounter.

    The engine emits lifecycle events; loops may emit domain-specific events.
    """
    type: str
    actor: Optional[str] = None
    target: Optional[str] = None
    message: str = ""
    data: Mapping[str, object] = field(default_factory=dict)
