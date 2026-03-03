from __future__ import annotations

from icos.kernel.core.actions import ActionRequest
from icos.kernel.events.types import Event
from icos.game.ecs import ECSRegistry
from icos.game.events import AI_ACTION_SELECTED, EventBus

from .common import actor_snapshot, living_enemies


INCAPACITATED = {"stunned", "paralyzed", "unconscious", "incapacitated"}


def ai_action_selection_system(world: ECSRegistry, bus: EventBus, context: dict[str, object]) -> None:
    actor_id = context.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        return

    heal_threshold_raw = context.get("heal_threshold", 0.35)
    heal_threshold = float(heal_threshold_raw) if isinstance(heal_threshold_raw, (int, float)) else 0.35

    actor = actor_snapshot(world, actor_id)

    if not actor.alive:
        action = ActionRequest(actor_id=actor_id, action_id="wait")
    elif any(name in INCAPACITATED for name in actor.conditions):
        action = ActionRequest(actor_id=actor_id, action_id="wait")
    elif actor.heals_remaining > 0 and actor.hp < actor.max_hp and (actor.hp / max(1, actor.max_hp)) <= heal_threshold:
        action = ActionRequest(actor_id=actor_id, action_id="heal", targets=(actor_id,), data={"heal_dice": actor.heal_dice})
    else:
        enemies = living_enemies(world, actor_id)
        if enemies and actor.attacks:
            target = enemies[0]
            action = ActionRequest(
                actor_id=actor_id,
                action_id="attack",
                targets=(target.id,),
                data={"attack_index": 0},
            )
        elif actor.alive:
            action = ActionRequest(actor_id=actor_id, action_id="defend")
        else:
            action = ActionRequest(actor_id=actor_id, action_id="wait")

    context["selected_action"] = action
    bus.publish(
        Event(
            type=AI_ACTION_SELECTED,
            actor=actor_id,
            target=action.targets[0] if action.targets else None,
            data={
                "actor_id": actor_id,
                "action_id": action.action_id,
                "action_type": action.action_id,
                "target_ids": list(action.targets),
                "action_data": dict(action.data),
            },
        )
    )
