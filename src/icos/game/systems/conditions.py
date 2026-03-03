from __future__ import annotations

from icos.game.ecs import ECSRegistry
from icos.game.events import CONDITION_TICKED, EventBus
from icos.kernel.events.types import Event


def condition_tick_system(world: ECSRegistry, bus: EventBus, context: dict[str, object]) -> None:
    actor_id = context.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        return

    bus.publish(
        Event(
            type=CONDITION_TICKED,
            actor=actor_id,
            data={"actor_id": actor_id},
        )
    )
