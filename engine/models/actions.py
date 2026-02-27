# engine/models/actions.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence, TypeAlias, Literal

from .core import DamageType

ActionType: TypeAlias = Literal["attack", "defend", "heal", "wait"]


@dataclass(frozen=True)
class AttackProfile:
    """
    A single attack option available to a combatant.
    This is "content-ish" (stats), not rules resolution.
    """
    name: str
    attack_bonus: int
    damage_dice: str
    damage_type: DamageType


@dataclass(frozen=True)
class ActionDeclaration:
    """
    A declared intent from a controller (player/combat AI/future LLM).

    Important: this contains NO outcomes. The engine (RulesEngine) is the source of truth
    for rolls, hits/misses, damage, and state changes.

    target_ids:
      - empty for self/neutral actions (defend/wait)
      - 1+ ids for targeted actions (attack, future spells, etc.)
    data:
      - small escape hatch for action parameters without refactoring the dataclass
        (ex: heal_dice, spell_id, move_to, etc.)
    """
    actor_id: str
    type: ActionType
    target_ids: Sequence[str] = ()
    attack_index: int = 0
    data: Mapping[str, object] = field(default_factory=dict)