from __future__ import annotations

from dataclasses import dataclass
from typing import List

from icos.tact.core.actions import ActionRequest
from icos.tact.core.state import EncounterState

from icos.game.runtime.actor import ActorBlueprint
from icos.game.systems import actor_snapshot, living_enemies
from icos.game.ecs import ECSRegistry
from icos.game.effects import AbilityDefinition


@dataclass(frozen=True)
class ActionRegistry:
    """Enumerates legal combat actions by ECS component state."""

    def list_actions(self, state: EncounterState[ActorBlueprint], actor_id: str) -> List[ActionRequest]:
        world = _world_from_state(state)
        actor = actor_snapshot(world, actor_id)

        if not actor.alive:
            return []
        if any(actor.conditions.get(c, 0) > 0 for c in ("stunned", "paralyzed", "unconscious", "incapacitated")):
            return [ActionRequest(actor_id=actor.id, action_id="wait")]

        actions: List[ActionRequest] = []

        for target in living_enemies(world, actor.id):
            actions.append(
                ActionRequest(
                    actor_id=actor.id,
                    action_id="attack",
                    targets=(target.id,),
                    data={"attack_index": 0},
                )
            )

        catalog = _ability_catalog(state)
        for ability_id in actor.ability_ids:
            ability = catalog.get(ability_id)
            if ability is None:
                continue
            target_rule = ability.target_rule.strip().lower()
            if target_rule in {"self", "caster", "source"}:
                actions.append(
                    ActionRequest(
                        actor_id=actor.id,
                        action_id="use_ability",
                        targets=(actor.id,),
                        data={"ability_id": ability_id},
                    )
                )
            else:
                for target in living_enemies(world, actor.id):
                    actions.append(
                        ActionRequest(
                            actor_id=actor.id,
                            action_id="use_ability",
                            targets=(target.id,),
                            data={"ability_id": ability_id},
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

        if actor.move_remaining > 0:
            actions.append(
                ActionRequest(
                    actor_id=actor.id,
                    action_id="move",
                    targets=(actor.id,),
                    data={"distance": min(10, actor.move_remaining)},
                )
            )

        actions.append(ActionRequest(actor_id=actor.id, action_id="wait"))
        return actions


def _world_from_state(state: EncounterState[ActorBlueprint]) -> ECSRegistry:
    world = state.data.get("ecs_world")
    if not isinstance(world, ECSRegistry):
        raise RuntimeError("ECS world unavailable. Encounter must be initialized first.")
    return world


def _ability_catalog(state: EncounterState[ActorBlueprint]) -> dict[str, AbilityDefinition]:
    catalog = state.data.get("ability_catalog")
    if not isinstance(catalog, dict):
        return {}

    out: dict[str, AbilityDefinition] = {}
    for key, value in catalog.items():
        if isinstance(key, str) and isinstance(value, AbilityDefinition):
            out[key] = value
    return out
