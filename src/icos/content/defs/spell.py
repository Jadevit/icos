from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import DamageSpec, ResourceRef


@dataclass(frozen=True)
class SpellDefinition:
    id: str
    endpoint: str
    api_index: str
    name: str

    level: int = 0
    school: ResourceRef | None = None
    casting_time: str = ""
    range: str = ""
    duration: str = ""
    concentration: bool = False
    ritual: bool = False

    components: tuple[str, ...] = field(default_factory=tuple)
    material: str = ""
    desc: tuple[str, ...] = field(default_factory=tuple)
    higher_level: tuple[str, ...] = field(default_factory=tuple)

    attack_type: str = ""
    damage_at_slot_level: dict[str, str] = field(default_factory=dict)
    damage_at_character_level: dict[str, str] = field(default_factory=dict)
    damage: tuple[DamageSpec, ...] = field(default_factory=tuple)

    classes: tuple[ResourceRef, ...] = field(default_factory=tuple)
    subclasses: tuple[ResourceRef, ...] = field(default_factory=tuple)

    url: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)
