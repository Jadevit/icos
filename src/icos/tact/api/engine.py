from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Mapping, Optional, TypeVar

from icos.tact.core.session import EncounterController, EncounterLoop, EncounterSession
from icos.tact.core.types import ActorLike
from icos.tact.events.types import Event

TActor = TypeVar("TActor", bound=ActorLike)
EventSink = Callable[[Event], None]


@dataclass
class KernelEngine(Generic[TActor]):
    """
    Stable public facade for running encounters.
    """
    def run(
        self,
        *,
        loop: EncounterLoop[TActor],
        actors: List[TActor],
        controllers: Mapping[str, EncounterController[TActor]],
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
    ) -> List[Event]:
        session: EncounterSession[TActor] = EncounterSession()
        return session.run(
            loop=loop,
            actors=actors,
            controllers=controllers,
            max_rounds=max_rounds,
            on_event=on_event,
        )
