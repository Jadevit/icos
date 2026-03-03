from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from icos.kernel.core.actor import Actor
from icos.kernel.core.state import EncounterState

from .common import JsonValue, to_json_value

STATE_SCHEMA_V1 = "icos.state.v1"

TActor = TypeVar("TActor", bound=Actor)


@dataclass(frozen=True)
class ActorStateV1:
    id: str
    name: str
    team: str
    alive: bool
    flags: tuple[str, ...] = field(default_factory=tuple)
    attrs: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "team": self.team,
            "alive": self.alive,
            "flags": list(self.flags),
            "attrs": self.attrs,
        }


@dataclass(frozen=True)
class StateRecordV1(Generic[TActor]):
    schema: str = STATE_SCHEMA_V1
    round: int = 1
    turn_index: int = 0
    turn_order: tuple[str, ...] = field(default_factory=tuple)
    actors: tuple[ActorStateV1, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "round": self.round,
            "turn_index": self.turn_index,
            "turn_order": list(self.turn_order),
            "actors": [a.to_dict() for a in self.actors],
        }


def actor_state_from_actor(actor: TActor) -> ActorStateV1:
    attrs: dict[str, JsonValue] = {}
    for key, value in sorted(vars(actor).items()):
        if key in {"id", "name", "team", "alive", "flags"}:
            continue
        attrs[key] = to_json_value(value)

    return ActorStateV1(
        id=actor.id,
        name=actor.name,
        team=actor.team,
        alive=bool(actor.alive),
        flags=tuple(sorted(actor.flags)),
        attrs=attrs,
    )


def state_record_from_state(state: EncounterState[TActor]) -> StateRecordV1[TActor]:
    actors = tuple(actor_state_from_actor(a) for a in sorted(state.actors, key=lambda x: x.id))
    return StateRecordV1(
        round=state.round_num,
        turn_index=state.turn_index,
        turn_order=tuple(state.turn_order),
        actors=actors,
    )


def state_record_from_actors(actors: list[TActor]) -> StateRecordV1[TActor]:
    initial = EncounterState(actors=list(actors))
    return state_record_from_state(initial)
