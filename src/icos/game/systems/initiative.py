from __future__ import annotations

from icos.content.defs.common import ability_mod
from icos.game.ecs import ECSRegistry, StatsComponent
from icos.game.events import INITIATIVE_ROLLED, TURN_ORDER_SET, EventBus
from icos.game.rules.dice import Dice
from icos.tact.events.types import Event

from .common import actor_snapshot


def initiative_system(world: ECSRegistry, bus: EventBus, context: dict[str, object]) -> None:
    dice = context.get("dice")
    if not isinstance(dice, Dice):
        raise TypeError("initiative_system requires Dice in context['dice']")

    rolls: list[tuple[int, int, str, str]] = []

    for entity_id in world.query_ids(StatsComponent):
        actor = actor_snapshot(world, entity_id)
        if not actor.alive:
            continue

        dex_mod = ability_mod(actor.dexterity)
        roll = dice.d20()
        total = roll + dex_mod
        rolls.append((total, dex_mod, entity_id, actor.name))

        bus.publish(
            Event(
                type=INITIATIVE_ROLLED,
                actor=entity_id,
                data={
                    "actor_id": entity_id,
                    "roll": roll,
                    "dex_mod": dex_mod,
                    "total": total,
                },
            )
        )

    rolls.sort(key=lambda item: (item[0], item[1], item[3], item[2]), reverse=True)
    order = [entity_id for _, _, entity_id, _ in rolls]

    bus.publish(
        Event(
            type=TURN_ORDER_SET,
            data={"turn_order": order},
        )
    )
