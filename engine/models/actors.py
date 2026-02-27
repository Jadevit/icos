# engine/models/actors.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .actions import AttackProfile
from .core import ability_mod


@dataclass
class Combatant:
    id: str
    name: str
    ac: int
    max_hp: int
    hp: int
    dex: int
    attacks: List[AttackProfile] = field(default_factory=list)

    @property
    def dex_mod(self) -> int:
        return ability_mod(self.dex)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def choose_basic_attack(self) -> AttackProfile:
        if not self.attacks:
            raise ValueError(f"{self.name} has no attacks configured.")
        return self.attacks[0]
