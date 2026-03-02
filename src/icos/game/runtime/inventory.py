from __future__ import annotations

import re
from dataclasses import dataclass, field

from icos.content.defs.item import EquipmentDefinition


_BONUS_RE = re.compile(r"\+(\d+)")


@dataclass(frozen=True)
class EquipmentModifiers:
    ac_bonus: int = 0
    attack_bonus: int = 0
    damage_bonus: int = 0
    heal_bonus: int = 0

    def plus(self, other: "EquipmentModifiers") -> "EquipmentModifiers":
        return EquipmentModifiers(
            ac_bonus=self.ac_bonus + other.ac_bonus,
            attack_bonus=self.attack_bonus + other.attack_bonus,
            damage_bonus=self.damage_bonus + other.damage_bonus,
            heal_bonus=self.heal_bonus + other.heal_bonus,
        )


@dataclass(frozen=True)
class EquippedItem:
    api_index: str
    name: str
    slot: str = "misc"
    modifiers: EquipmentModifiers = field(default_factory=EquipmentModifiers)


@dataclass
class Inventory:
    items: list[EquippedItem] = field(default_factory=list)

    def equip(self, item: EquippedItem) -> None:
        self.items.append(item)

    def equipped_names(self) -> list[str]:
        return [i.name for i in self.items]

    @property
    def modifiers(self) -> EquipmentModifiers:
        out = EquipmentModifiers()
        for item in self.items:
            out = out.plus(item.modifiers)
        return out


def equipment_to_modifiers(equipment: EquipmentDefinition) -> EquipmentModifiers:
    """Heuristic mapping from content equipment definitions to runtime combat modifiers."""

    magic_bonus = _extract_magic_bonus(equipment.name)

    ac_bonus = 0
    armor_category = equipment.armor_category.lower().strip()
    if armor_category == "shield":
        ac_bonus += equipment.armor_class_base if equipment.armor_class_base > 0 else 2
    if magic_bonus > 0 and armor_category:
        ac_bonus += magic_bonus

    attack_bonus = 0
    damage_bonus = 0
    if equipment.weapon_category.strip():
        attack_bonus += magic_bonus
        damage_bonus += magic_bonus

    heal_bonus = 0
    n = equipment.name.lower()
    if "healing" in n or "healer" in n:
        heal_bonus += magic_bonus if magic_bonus > 0 else 1

    return EquipmentModifiers(
        ac_bonus=ac_bonus,
        attack_bonus=attack_bonus,
        damage_bonus=damage_bonus,
        heal_bonus=heal_bonus,
    )


def _extract_magic_bonus(name: str) -> int:
    m = _BONUS_RE.search(name)
    if m is None:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0
