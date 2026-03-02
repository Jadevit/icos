from __future__ import annotations

from dataclasses import dataclass
from typing import List

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.state import EncounterState

from icos.game.runtime.actor import Combatant
from icos.game.combat.targeting import living_enemies


@dataclass(frozen=True)
class ActionRegistry:
    """Enumerates legal combat actions for the current actor/state."""

    def list_actions(self, state: EncounterState[Combatant], actor: Combatant) -> List[ActionRequest]:
        if not actor.alive:
            return []
        if any(actor.has_condition(c) for c in ("stunned", "paralyzed", "unconscious", "incapacitated")):
            return [ActionRequest(actor_id=actor.id, action_id="wait")]

        actions: List[ActionRequest] = []

        for target in living_enemies(state, actor):
            actions.append(
                ActionRequest(
                    actor_id=actor.id,
                    action_id="attack",
                    targets=(target.id,),
                    data={"attack_index": 0},
                )
            )

        actions.append(ActionRequest(actor_id=actor.id, action_id="defend"))

        if actor.heals_remaining > 0 and actor.hp < actor.max_hp:
            actions.append(
                ActionRequest(
                    actor_id=actor.id,
                    action_id="heal",
                    targets=(actor.id,),
                    data={"heal_dice": actor.heal_dice},
                )
            )

        actions.append(ActionRequest(actor_id=actor.id, action_id="wait"))
        return actions
