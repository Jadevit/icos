from __future__ import annotations

from icos.content.defs.item import EquipmentDefinition
from icos.game.runtime.inventory import EquippedItem, equipment_to_modifiers


def equipment_to_equipped_item(equipment: EquipmentDefinition, *, slot: str = "misc") -> EquippedItem:
    return EquippedItem(
        api_index=equipment.api_index,
        name=equipment.name,
        slot=slot,
        modifiers=equipment_to_modifiers(equipment),
    )
