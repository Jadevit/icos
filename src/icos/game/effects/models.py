from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True)
class DamageEffect:
    amount: str
    damage_type: str
    target: str = "target"


@dataclass(frozen=True)
class HealEffect:
    amount: str
    target: str = "self"


@dataclass(frozen=True)
class ApplyConditionEffect:
    condition: str
    duration: int = 1
    target: str = "target"


@dataclass(frozen=True)
class MoveEffect:
    distance: int
    target: str = "self"


@dataclass(frozen=True)
class ModifyStatEffect:
    bonuses: dict[str, int] = field(default_factory=dict)
    target: str = "self"


@dataclass(frozen=True)
class RollCheckEffect:
    stat: str
    dc: int
    target: str = "target"
    bonus: int = 0
    on_success: tuple["EffectSpec", ...] = field(default_factory=tuple)
    on_failure: tuple["EffectSpec", ...] = field(default_factory=tuple)


EffectSpec: TypeAlias = (
    DamageEffect
    | HealEffect
    | ApplyConditionEffect
    | MoveEffect
    | ModifyStatEffect
    | RollCheckEffect
)
