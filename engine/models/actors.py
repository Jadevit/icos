# engine/models/actors.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from .actions import AttackProfile
from .core import ability_mod


@dataclass
class Combatant:
    id: str
    name: str
    team: str
    ac: int
    max_hp: int
    hp: int
    dex: int
    attacks: List[AttackProfile] = field(default_factory=list)
    flags: Set[str] = field(default_factory=set)  # e.g. {"defending"}

    @property
    def dex_mod(self) -> int:
        return ability_mod(self.dex)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def choose_attack(self, index: int = 0) -> AttackProfile:
        if not self.attacks:
            raise ValueError(f"{self.name} has no attacks configured.")
        if index < 0 or index >= len(self.attacks):
            raise IndexError(f"{self.name} has no attack at index {index}.")
        return self.attacks[index]
