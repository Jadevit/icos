from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Mapping, Optional, Protocol, TypeVar

from .actions import ActionRequest
from .actor import Actor
from .state import EncounterState
from ..events import (
    Event,
    ENCOUNTER_ENDED,
    ENCOUNTER_STARTED,
    TURN_STARTED,
)

TActor = TypeVar("TActor", bound=Actor)

# Contravariant: a controller that can handle a more general Actor
# can be used where a controller for a more specific Actor is expected.
TActor_contra = TypeVar("TActor_contra", bound=Actor, contravariant=True)

EventSink = Callable[[Event], None]


class EncounterController(Protocol, Generic[TActor_contra]):
    def choose_action(self, state: EncounterState[TActor_contra], actor_id: str) -> ActionRequest: ...


class EncounterLoop(Protocol, Generic[TActor_contra]):
    def init_encounter(self, state: EncounterState[TActor_contra]) -> List[Event]: ...
    def before_turn(self, state: EncounterState[TActor_contra], actor_id: str) -> List[Event]: ...
    def resolve_action(self, state: EncounterState[TActor_contra], action: ActionRequest) -> List[Event]: ...
    def is_over(self, state: EncounterState[TActor_contra]) -> bool: ...
    def outcome(self, state: EncounterState[TActor_contra]) -> Optional[str]: ...
    def finalize(self, state: EncounterState[TActor_contra]) -> List[Event]: ...


@dataclass
class EncounterSession(Generic[TActor]):
    """
    Generic encounter runner. The engine owns the loop; the game supplies logic via EncounterLoop.
    """

    def run(
        self,
        loop: EncounterLoop[TActor],
        actors: List[TActor],
        controllers: Mapping[str, EncounterController[TActor]],
        *,
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
    ) -> List[Event]:
        state = EncounterState[TActor](actors=actors)
        log: List[Event] = []

        def emit(ev: Event) -> None:
            log.append(ev)
            if on_event is not None and ev.message:
                on_event(ev)

        def emit_many(events: List[Event]) -> None:
            for e in events:
                emit(e)

        emit(Event(type=ENCOUNTER_STARTED, message="Encounter started."))
        emit_many(loop.init_encounter(state))

        while not loop.is_over(state) and state.round_num <= max_rounds:
            actor_id = state.current_actor_id()
            actor = state.get(actor_id)

            if not actor.alive:
                state.advance_turn()
                continue

            emit(
                Event(
                    type=TURN_STARTED,
                    actor=actor.id,
                    message=f"--- Round {state.round_num}, {actor.name} turn ---",
                    data={"round": state.round_num},
                )
            )

            emit_many(loop.before_turn(state, actor.id))

            controller = controllers.get(actor.id)
            action = (
                controller.choose_action(state, actor.id)
                if controller is not None
                else ActionRequest(actor_id=actor.id, action_id="wait")
            )

            emit_many(loop.resolve_action(state, action))
            state.advance_turn()

        emit_many(loop.finalize(state))

        out = loop.outcome(state)
        emit(Event(type=ENCOUNTER_ENDED, message=f"Encounter ended. Outcome: {out}" if out else "Encounter ended."))
        return log