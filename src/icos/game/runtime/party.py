from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Generic, List, Optional, TypeVar

from icos.tact.core.session import EncounterController
from icos.tact.core.types import ActorLike
from icos.tact.events.types import Event

TActor = TypeVar("TActor", bound=ActorLike)
EventSink = Callable[[Event], None]


@dataclass
class EncounterPlan(Generic[TActor]):
    actors: List[TActor] = field(default_factory=list)
    controllers: Dict[str, EncounterController[TActor]] = field(default_factory=dict)
    max_rounds: int = 50
    on_event: Optional[EventSink] = None

    def add(
        self,
        actor: TActor,
        controller: Optional[EncounterController[TActor]] = None,
    ) -> "EncounterPlan[TActor]":
        self.actors.append(actor)
        if controller is not None:
            self.controllers[actor.id] = controller
        return self
