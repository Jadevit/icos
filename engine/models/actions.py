# engine/models/actions.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Sequence

from .core import DamageType


@dataclass(frozen=True)
class AttackProfile:
    name: str
    attack_bonus: int
    damage_dice: str
    damage_type: DamageType


ActionType = Literal["attack", "defend", "heal", "wait"]


@dataclass(frozen=True)
class ActionDeclaration:
    """
    Declared intent. Rules engine turns this into facts/events + state changes.
    """

    actor_id: str
    type: ActionType
    target_ids: Sequence[str] = ()
    attack_index: int = 0
    data: Dict[str, object] = field(default_factory=dict)
