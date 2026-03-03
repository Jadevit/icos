from __future__ import annotations

from dataclasses import dataclass, field

from .models import EffectSpec


@dataclass(frozen=True)
class AbilityDefinition:
    id: str
    name: str
    target_rule: str = "target"
    range: str = "melee"
    effects: tuple[EffectSpec, ...] = field(default_factory=tuple)
