# engine/models/actions.py
from __future__ import annotations

from dataclasses import dataclass

from .core import DamageType


@dataclass(frozen=True)
class AttackProfile:
    name: str
    attack_bonus: int
    damage_dice: str
    damage_type: DamageType
