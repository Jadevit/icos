from __future__ import annotations

"""Mutable runtime encounter state used by simulation systems."""

from dataclasses import dataclass, field
from typing import Dict, Generic, List, TypeVar

from .types import ActorLike

TActor = TypeVar("TActor", bound=ActorLike)


@dataclass
class EncounterState(Generic[TActor]):
    """
    Generic encounter state owned by the kernel runner.
    Gameplay layers define what "over" means and how actions mutate state.
    """
    actors: List[TActor]
    round_num: int = 1
    turn_index: int = 0
    turn_order: List[str] = field(default_factory=list)
    data: Dict[str, object] = field(default_factory=dict)

    _by_id: Dict[str, TActor] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {a.id: a for a in self.actors}
        if len(self._by_id) != len(self.actors):
            raise ValueError("Duplicate actor ids in encounter state.")

    def get(self, actor_id: str) -> TActor:
        try:
            return self._by_id[actor_id]
        except KeyError as e:
            raise KeyError(f"Actor not found: {actor_id}") from e

    def current_actor_id(self) -> str:
        if not self.turn_order:
            raise ValueError("turn_order not set.")
        return self.turn_order[self.turn_index]

    def actor_ids(self) -> List[str]:
        return [a.id for a in self.actors]

    def advance_turn(self) -> None:
        if not self.turn_order:
            raise ValueError("turn_order not set.")
        self.turn_index += 1
        if self.turn_index >= len(self.turn_order):
            self.turn_index = 0
            self.round_num += 1
