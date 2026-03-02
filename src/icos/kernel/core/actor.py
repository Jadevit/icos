from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set


@dataclass
class Actor:
    """
    Generic encounter participant.

    Tact only cares that:
      - Actors have identity (id)
      - They can be alive/dead (alive)
      - They can have tags/flags for systems to interpret (flags)

    Games extend this class (or wrap it) with domain-specific state.
    """
    id: str
    name: str
    team: str = "neutral"
    flags: Set[str] = field(default_factory=set)
    alive: bool = True