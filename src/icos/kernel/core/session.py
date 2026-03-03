from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Mapping, Optional, Protocol, TypeVar

from .actions import ActionRequest
from .actor import Actor
from .state import EncounterState
from ..events import (
    ACTION_APPLIED,
    ACTION_REQUESTED,
    ACTION_RESOLVED,
    ACTION_VALIDATED,
    ENCOUNTER_ENDED,
    ENCOUNTER_STARTED,
    EVENT_SCHEMA_V1,
    TURN_ENDED,
    TURN_SKIPPED,
    TURN_STARTED,
    Event,
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

    Phase-0 contract guarantees:
    - every chosen action emits requested/validated/resolved/applied lifecycle events
    - all emitted events carry deterministic structured metadata in `data`
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

        event_seq = 0
        action_seq = 0

        def emit(ev: Event) -> Event:
            nonlocal event_seq
            event_seq += 1

            payload = dict(ev.data)
            payload.setdefault("event_schema", EVENT_SCHEMA_V1)
            payload.setdefault("event_seq", event_seq)
            payload.setdefault("round", state.round_num)
            payload.setdefault("turn_index", state.turn_index)

            canonical = Event(
                type=ev.type,
                actor=ev.actor,
                target=ev.target,
                message=ev.message,
                data=payload,
            )

            log.append(canonical)
            if on_event is not None:
                on_event(canonical)
            return canonical

        def emit_many(events: List[Event], *, action_id: int | None = None) -> None:
            for e in events:
                if action_id is not None:
                    e = self._attach_action_context(e, action_id)
                emit(e)

        emit(Event(type=ENCOUNTER_STARTED, message="Encounter started.", data={"phase": "encounter"}))
        emit_many(loop.init_encounter(state))

        while not loop.is_over(state) and state.round_num <= max_rounds:
            actor_id = state.current_actor_id()
            actor = state.get(actor_id)

            if not actor.alive:
                emit(
                    Event(
                        type=TURN_SKIPPED,
                        actor=actor.id,
                        message=f"Skipping {actor.name}; actor is not alive.",
                        data={"reason": "actor_not_alive"},
                    )
                )
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
            source = "controller" if controller is not None else "default_wait"
            raw_action = (
                controller.choose_action(state, actor.id)
                if controller is not None
                else ActionRequest(actor_id=actor.id, action_id="wait")
            )

            action_seq += 1
            emit(
                Event(
                    type=ACTION_REQUESTED,
                    actor=actor.id,
                    message="Action requested.",
                    data={
                        "action_seq": action_seq,
                        "source": source,
                        "action": self._action_to_payload(raw_action),
                    },
                )
            )

            action, valid, issues = self._normalize_action(state, actor.id, raw_action)
            emit(
                Event(
                    type=ACTION_VALIDATED,
                    actor=actor.id,
                    message="Action validated." if valid else "Action invalid; replaced with wait.",
                    data={
                        "action_seq": action_seq,
                        "valid": valid,
                        "issues": issues,
                        "action": self._action_to_payload(action),
                    },
                )
            )

            resolved = loop.resolve_action(state, action)
            emit_many(resolved, action_id=action_seq)
            emit(
                Event(
                    type=ACTION_RESOLVED,
                    actor=actor.id,
                    message="Action resolved.",
                    data={
                        "action_seq": action_seq,
                        "emitted_event_count": len(resolved),
                        "emitted_event_types": [e.type for e in resolved],
                    },
                )
            )

            emit(
                Event(
                    type=TURN_ENDED,
                    actor=actor.id,
                    message=f"End of {actor.name} turn.",
                    data={"action_seq": action_seq},
                )
            )

            state.advance_turn()
            emit(
                Event(
                    type=ACTION_APPLIED,
                    actor=actor.id,
                    message="Post-action state applied.",
                    data={
                        "action_seq": action_seq,
                        "state": self._state_summary(state),
                    },
                )
            )

        emit_many(loop.finalize(state))

        out = loop.outcome(state)
        emit(
            Event(
                type=ENCOUNTER_ENDED,
                message=f"Encounter ended. Outcome: {out}" if out else "Encounter ended.",
                data={"outcome": out},
            )
        )
        return log

    @staticmethod
    def _attach_action_context(event: Event, action_seq: int) -> Event:
        payload = dict(event.data)
        payload.setdefault("action_seq", action_seq)
        return Event(
            type=event.type,
            actor=event.actor,
            target=event.target,
            message=event.message,
            data=payload,
        )

    @staticmethod
    def _action_to_payload(action: ActionRequest) -> dict[str, object]:
        return {
            "actor_id": action.actor_id,
            "action_id": action.action_id,
            "targets": [str(t) for t in action.targets],
            "data": dict(action.data),
        }

    @staticmethod
    def _normalize_action(
        state: EncounterState[TActor],
        actor_id: str,
        action: ActionRequest,
    ) -> tuple[ActionRequest, bool, list[str]]:
        issues: list[str] = []

        action_id = str(action.action_id).strip().lower()
        if not action_id:
            issues.append("missing_action_id")
            action_id = "wait"

        if action.actor_id != actor_id:
            issues.append("actor_mismatch")

        known_ids = {a.id for a in state.actors}
        targets = tuple(str(t) for t in action.targets)
        bad_targets = [t for t in targets if t not in known_ids]
        if bad_targets:
            issues.append(f"unknown_targets:{','.join(sorted(bad_targets))}")

        data = dict(action.data)

        if issues:
            return ActionRequest(actor_id=actor_id, action_id="wait"), False, issues

        return (
            ActionRequest(
                actor_id=actor_id,
                action_id=action_id,
                targets=targets,
                data=data,
            ),
            True,
            [],
        )

    @staticmethod
    def _state_summary(state: EncounterState[TActor]) -> dict[str, object]:
        actors = sorted(state.actors, key=lambda a: a.id)
        return {
            "round": state.round_num,
            "turn_index": state.turn_index,
            "turn_order": list(state.turn_order),
            "actors": [
                {
                    "id": a.id,
                    "team": a.team,
                    "alive": bool(a.alive),
                    "flags": sorted(a.flags),
                }
                for a in actors
            ],
        }
