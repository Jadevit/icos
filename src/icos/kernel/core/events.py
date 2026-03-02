from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional


@dataclass(frozen=True)
class Event:
    """
    Immutable record of something that happened.

    `type` is intentionally open-ended (string). Tact defines some common
    lifecycle event names, but games can emit anything they want.
    """
    type: str
    actor: Optional[str] = None
    target: Optional[str] = None
    message: str = ""
    data: Mapping[str, object] = field(default_factory=dict)


# Convention (not enforcement): common engine lifecycle event names
ROUND_STARTED = "round_started"
ROUND_ENDED = "round_ended"
TURN_STARTED = "turn_started"
TURN_ENDED = "turn_ended"
ENCOUNTER_STARTED = "encounter_started"
ENCOUNTER_ENDED = "encounter_ended"

ACTION_REQUESTED = "action_requested"      # controller picked an action
ACTION_VALIDATED = "action_validated"
ACTION_RESOLVED = "action_resolved"        # produced outcome/events