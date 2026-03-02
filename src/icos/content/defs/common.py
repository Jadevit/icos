from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias

DamageType: TypeAlias = str
JsonMap: TypeAlias = Mapping[str, Any]


@dataclass(frozen=True)
class ResourceRef:
    """Reference to a related codex resource."""

    index: str
    name: str
    url: str = ""


@dataclass(frozen=True)
class AbilityScores:
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


@dataclass(frozen=True)
class ArmorClassEntry:
    value: int
    ac_type: str = ""
    armor: tuple[ResourceRef, ...] = field(default_factory=tuple)
    condition: str = ""
    spell: ResourceRef | None = None


@dataclass(frozen=True)
class DamageSpec:
    damage_dice: str
    damage_type: ResourceRef | None = None


@dataclass(frozen=True)
class ActionTextBlock:
    name: str
    desc: str


@dataclass(frozen=True)
class SpeedProfile:
    values: dict[str, str]


def ability_mod(score: int) -> int:
    """5e-style ability modifier helper used by combat/check systems."""

    return (score - 10) // 2
