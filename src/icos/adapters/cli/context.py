from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from icos.app.services.engine import GameEngine
from icos.game.runtime.actor import ActorBlueprint
from icos.game.runtime.party import EncounterPlan


@dataclass
class DevContext:
    engine: GameEngine[ActorBlueprint]
    encounter: Optional[EncounterPlan[ActorBlueprint]] = None
    verbose_events: bool = False
    last_error: Optional[str] = None
    vars: dict[str, object] = field(default_factory=dict)
