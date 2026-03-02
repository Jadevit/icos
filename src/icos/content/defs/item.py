from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import ResourceRef


@dataclass(frozen=True)
class EquipmentDefinition:
    id: str
    endpoint: str
    api_index: str
    name: str

    equipment_category: ResourceRef | None = None
    gear_category: ResourceRef | None = None
    armor_category: str = ""
    weapon_category: str = ""
    weapon_range: str = ""
    cost_quantity: int = 0
    cost_unit: str = ""
    weight: float = 0.0

    damage_dice: str = ""
    damage_type: ResourceRef | None = None

    armor_class_base: int = 0
    armor_class_dex_bonus: bool = False
    armor_class_max_bonus: int | None = None

    properties: tuple[ResourceRef, ...] = field(default_factory=tuple)
    desc: tuple[str, ...] = field(default_factory=tuple)

    url: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)
