# engine/systems/ai/interface.py
from __future__ import annotations

from typing import Protocol

from ...models import ActionDeclaration
from ...state import CombatState


class CombatController(Protocol):
    """
    A controller chooses an ActionDeclaration for a combatant.

    - PlayerController: asks the user
    - PlannerController: evaluates legal actions and picks the best
    - Future: LLMController (still outputs ActionDeclaration, never outcomes)
    """

    def choose_action(self, state: CombatState, actor_id: str) -> ActionDeclaration: ...