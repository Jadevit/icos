from __future__ import annotations

from typing import Protocol, Set, runtime_checkable


@runtime_checkable
class ActorLike(Protocol):
    """Structural actor shape required by kernel session/state/replay logic."""

    id: str
    name: str
    team: str
    alive: bool
    flags: Set[str]
