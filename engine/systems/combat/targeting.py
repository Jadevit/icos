# engine/systems/combat/targeting.py
from __future__ import annotations

from typing import Optional

from ...state import CombatState
from ...models import Combatant


def first_alive_enemy(state: CombatState, actor: Combatant) -> Optional[Combatant]:
    """
    Deterministic, dumb targeting:
    pick the first alive combatant on a different team.
    """
    for c in state.combatants:
        if c.alive and c.team != actor.team:
            return c
    return None
