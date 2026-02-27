# engine/systems/actions/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ...models import ActionDeclaration, Combatant
from ...state import CombatState


@dataclass(frozen=True)
class ActionRegistry:
    """
    Enumerate legal actions for an actor given the current state.

    This is the key extension point:
      - movement will add move actions
      - spells will add cast actions
      - items will add use-item actions

    The RulesEngine remains the authority for outcomes.
    """

    def list_actions(self, state: CombatState, actor: Combatant) -> list[ActionDeclaration]:
        if not actor.alive:
            return []

        actions: list[ActionDeclaration] = []

        # Attack: any alive enemy is a legal target.
        # (Target choice is a controller/AI problem, not a rules problem.)
        for t in state.combatants:
            if t.alive and t.team != actor.team:
                actions.append(
                    ActionDeclaration(
                        actor_id=actor.id,
                        type="attack",
                        target_ids=(t.id,),
                        attack_index=0,  # v1: always use first attack
                    )
                )

        # Defend is always legal.
        actions.append(ActionDeclaration(actor_id=actor.id, type="defend"))

        # Heal: legal only if you have charges and you're not already full.
        if actor.heals_remaining > 0 and actor.hp < actor.max_hp:
            actions.append(
                ActionDeclaration(
                    actor_id=actor.id,
                    type="heal",
                    target_ids=(actor.id,),
                    data={"heal_dice": actor.heal_dice},
                )
            )

        # Wait is always legal.
        actions.append(ActionDeclaration(actor_id=actor.id, type="wait"))

        return actions