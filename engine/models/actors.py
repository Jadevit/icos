# engine/models/actors.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from .actions import AttackProfile
from .core import ability_mod


@dataclass
class Combatant:
    """
    Runtime combatant state (mutable during an encounter).

    This is NOT a full character sheet.
    team:
      - used for victory conditions and target filtering
      - 1v1 is just two combatants on different teams; no special casing
    flags:
      - temporary status markers
    """
    id: str
    name: str
    team: str

    ac: int
    max_hp: int
    hp: int
    dex: int

    attacks: List[AttackProfile] = field(default_factory=list)
    flags: Set[str] = field(default_factory=set)  # e.g. {"defending"}

    # Temporary per-battle resources (stand-in until items/potions exist)
    heals_remaining: int = 0
    heal_dice: str = "1d8+2"

    def __post_init__(self) -> None:
        # Small guardrails to prevent weird state bugs.
        if self.max_hp <= 0:
            raise ValueError("max_hp must be > 0")
        if self.ac <= 0:
            raise ValueError("ac must be > 0")
        if self.hp < 0:
            self.hp = 0
        if self.hp > self.max_hp:
            self.hp = self.max_hp

    @property
    def dex_mod(self) -> int:
        return ability_mod(self.dex)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def choose_attack(self, index: int = 0) -> AttackProfile:
        """
        Select an attack profile by index.
        Keeping this on Combatant avoids leaking list indexing logic into rules/controllers.
        """
        if not self.attacks:
            raise ValueError(f"{self.name} has no attacks configured.")
        if index < 0 or index >= len(self.attacks):
            raise IndexError(f"{self.name} has no attack at index {index}.")
        return self.attacks[index]