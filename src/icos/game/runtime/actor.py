from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from icos.kernel.core.actor import Actor

from icos.content.defs.common import DamageType, ability_mod
from icos.game.runtime.inventory import EquippedItem, Inventory


@dataclass(frozen=True)
class AttackProfile:
    name: str
    attack_bonus: int
    damage_dice: str
    damage_type: DamageType
    attack_kind: str = "melee"


@dataclass
class Combatant(Actor):
    """Combat-specific actor state layered on top of Tact Actor."""

    ac: int = 10
    max_hp: int = 1
    hp: int = 1
    dex: int = 10
    attacks: List[AttackProfile] = field(default_factory=list)

    heals_remaining: int = 0
    heal_dice: str = "1d8+2"
    conditions: Dict[str, int] = field(default_factory=dict)
    inventory: Inventory = field(default_factory=Inventory)

    def __post_init__(self) -> None:
        if self.max_hp <= 0:
            raise ValueError("max_hp must be > 0")
        if self.ac <= 0:
            raise ValueError("ac must be > 0")

        if self.hp < 0:
            self.hp = 0
        if self.hp > self.max_hp:
            self.hp = self.max_hp

        self.alive = self.hp > 0

    @property
    def dex_mod(self) -> int:
        return ability_mod(self.dex)

    @property
    def effective_ac(self) -> int:
        return max(1, self.ac + self.inventory.modifiers.ac_bonus)

    @property
    def equipment_attack_bonus(self) -> int:
        return self.inventory.modifiers.attack_bonus

    @property
    def equipment_damage_bonus(self) -> int:
        return self.inventory.modifiers.damage_bonus

    @property
    def equipment_heal_bonus(self) -> int:
        return self.inventory.modifiers.heal_bonus

    def set_hp(self, value: int) -> None:
        self.hp = max(0, min(self.max_hp, value))
        self.alive = self.hp > 0

    def choose_attack(self, index: int = 0) -> AttackProfile:
        if not self.attacks:
            raise ValueError(f"{self.name} has no attacks configured.")
        if index < 0 or index >= len(self.attacks):
            raise IndexError(f"{self.name} has no attack at index {index}.")
        return self.attacks[index]

    def add_condition(self, name: str, turns: int = 1) -> None:
        key = name.strip().lower()
        if not key:
            return
        new_turns = max(1, turns)
        self.conditions[key] = max(self.conditions.get(key, 0), new_turns)

    def clear_condition(self, name: str) -> None:
        key = name.strip().lower()
        if key:
            self.conditions.pop(key, None)

    def has_condition(self, name: str) -> bool:
        key = name.strip().lower()
        return self.conditions.get(key, 0) > 0

    def tick_conditions(self) -> List[str]:
        expired: List[str] = []
        for key in list(self.conditions):
            self.conditions[key] -= 1
            if self.conditions[key] <= 0:
                expired.append(key)
                del self.conditions[key]
        return expired

    def equip_item(self, item: EquippedItem) -> None:
        self.inventory.equip(item)
