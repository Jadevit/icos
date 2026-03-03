from __future__ import annotations

from icos.game.ecs import ECSRegistry, EncounterComponent
from icos.game.events import TURN_ADVANCED, TURN_CONTEXT_RESET, EventBus
from icos.kernel.events.types import Event


def turn_start_system(world: ECSRegistry, bus: EventBus, context: dict[str, object]) -> None:
    actor_id = context.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        return

    bus.publish(
        Event(
            type=TURN_CONTEXT_RESET,
            actor=actor_id,
            data={"actor_id": actor_id},
        )
    )


def turn_advance_system(world: ECSRegistry, bus: EventBus, context: dict[str, object]) -> None:
    encounter_entity = context.get("encounter_entity")
    if not isinstance(encounter_entity, str):
        return

    if not world.has_component(encounter_entity, EncounterComponent):
        return

    encounter = world.get_component(encounter_entity, EncounterComponent)
    order = list(encounter.turn_order)
    if not order:
        return

    old_round = encounter.round_num
    old_index = encounter.turn_index

    next_index = old_index + 1
    next_round = old_round
    if next_index >= len(order):
        next_index = 0
        next_round += 1

    bus.publish(
        Event(
            type=TURN_ADVANCED,
            data={
                "from_round": old_round,
                "from_turn_index": old_index,
                "to_round": next_round,
                "to_turn_index": next_index,
            },
        )
    )
