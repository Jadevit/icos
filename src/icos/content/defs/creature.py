from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import AbilityScores, ActionTextBlock, ArmorClassEntry, DamageSpec, SpeedProfile


@dataclass(frozen=True)
class MonsterAction(ActionTextBlock):
    attack_bonus: int | None = None
    attack_kind: str = ""
    damages: tuple[DamageSpec, ...] = field(default_factory=tuple)
    nested_actions: tuple[ActionTextBlock, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MonsterDefinition:
    id: str
    endpoint: str
    api_index: str
    name: str

    creature_type: str = ""
    subtype: str = ""
    size: str = ""
    alignment: str = ""
    languages: str = ""

    challenge_rating: float = 0.0
    xp: int = 0
    proficiency_bonus: int = 0

    armor_class: tuple[ArmorClassEntry, ...] = field(default_factory=tuple)
    hit_points: int = 1
    hit_dice: str = ""
    hit_points_roll: str = ""

    abilities: AbilityScores = field(
        default_factory=lambda: AbilityScores(
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
        )
    )
    speed: SpeedProfile = field(default_factory=lambda: SpeedProfile(values={}))

    senses: dict[str, Any] = field(default_factory=dict)
    damage_immunities: tuple[str, ...] = field(default_factory=tuple)
    damage_resistances: tuple[str, ...] = field(default_factory=tuple)
    damage_vulnerabilities: tuple[str, ...] = field(default_factory=tuple)
    condition_immunities: tuple[str, ...] = field(default_factory=tuple)

    actions: tuple[MonsterAction, ...] = field(default_factory=tuple)
    special_abilities: tuple[ActionTextBlock, ...] = field(default_factory=tuple)
    reactions: tuple[ActionTextBlock, ...] = field(default_factory=tuple)
    legendary_actions: tuple[ActionTextBlock, ...] = field(default_factory=tuple)

    image: str = ""
    url: str = ""
    updated_at: str = ""

    raw_json: dict[str, Any] = field(default_factory=dict)
