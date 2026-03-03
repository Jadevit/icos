from __future__ import annotations

from icos.game.ecs import (
    ConditionComponent,
    ECSRegistry,
    EncounterComponent,
    FlagComponent,
    HealProfileComponent,
    HealthComponent,
    InitiativeComponent,
    MovementComponent,
    PositionComponent,
    StatsComponent,
)
from icos.game.events import (
    CONDITION_APPLIED,
    CONDITION_EXPIRED,
    CONDITION_TICKED,
    DAMAGE_APPLIED,
    ENTITY_DIED,
    HEAL_APPLIED,
    HP_CHANGED,
    INITIATIVE_ROLLED,
    MOVED,
    STATS_MODIFIED,
    TURN_ADVANCED,
    TURN_CONTEXT_RESET,
    TURN_ORDER_SET,
)
from icos.kernel.events.types import Event


def apply_event_to_world(
    world: ECSRegistry,
    event: Event,
    *,
    encounter_entity: str,
) -> list[Event]:
    spawned: list[Event] = []

    if event.type == TURN_ORDER_SET:
        encounter = _encounter(world, encounter_entity)
        payload = event.data.get("turn_order")
        if isinstance(payload, list):
            encounter.turn_order = [str(v) for v in payload]
            encounter.turn_index = 0
            encounter.round_num = 1
        return spawned

    if event.type == TURN_ADVANCED:
        encounter = _encounter(world, encounter_entity)
        to_round = event.data.get("to_round")
        to_index = event.data.get("to_turn_index")
        try:
            encounter.round_num = int(to_round)
            encounter.turn_index = int(to_index)
        except (TypeError, ValueError):
            pass
        return spawned

    if event.type == TURN_CONTEXT_RESET and event.actor:
        if world.has_component(event.actor, FlagComponent):
            flags = world.get_component(event.actor, FlagComponent)
            flags.flags.discard("defending")

        if world.has_component(event.actor, ConditionComponent):
            world.get_component(event.actor, ConditionComponent).turns.pop("defending", None)

        if world.has_component(event.actor, MovementComponent):
            move = world.get_component(event.actor, MovementComponent)
            move.remaining = int(move.speed)

        return spawned

    if event.type == CONDITION_TICKED and event.actor:
        if not world.has_component(event.actor, ConditionComponent):
            return spawned
        comp = world.get_component(event.actor, ConditionComponent)
        for key in list(comp.turns):
            comp.turns[key] -= 1
            if comp.turns[key] <= 0:
                del comp.turns[key]
                if key == "defending" and world.has_component(event.actor, FlagComponent):
                    world.get_component(event.actor, FlagComponent).flags.discard("defending")
                spawned.append(
                    Event(
                        type=CONDITION_EXPIRED,
                        actor=event.actor,
                        data={
                            "actor_id": event.actor,
                            "condition": key,
                        },
                    )
                )
        return spawned

    if event.type == CONDITION_APPLIED and event.target:
        condition = str(event.data.get("condition", "")).strip().lower()
        if not condition:
            return spawned

        duration_raw = event.data.get("duration", 1)
        try:
            duration = max(1, int(duration_raw))
        except (TypeError, ValueError):
            duration = 1

        if world.has_component(event.target, ConditionComponent):
            comp = world.get_component(event.target, ConditionComponent)
        else:
            comp = ConditionComponent()
            world.add_component(event.target, comp)

        comp.turns[condition] = max(comp.turns.get(condition, 0), duration)
        if condition == "defending" and world.has_component(event.target, FlagComponent):
            world.get_component(event.target, FlagComponent).flags.add("defending")
        return spawned

    if event.type == INITIATIVE_ROLLED and event.actor:
        total = event.data.get("total", 0)
        dex_mod = event.data.get("dex_mod", 0)
        try:
            init = InitiativeComponent(total=int(total), dex_mod=int(dex_mod))
        except (TypeError, ValueError):
            init = InitiativeComponent(total=0, dex_mod=0)

        if world.has_component(event.actor, InitiativeComponent):
            world.add_component(event.actor, init)
        else:
            world.add_component(event.actor, init)
        return spawned

    if event.type == DAMAGE_APPLIED and event.target:
        if not world.has_component(event.target, HealthComponent):
            return spawned

        health = world.get_component(event.target, HealthComponent)
        amount = _as_non_negative_int(event.data.get("amount", 0))

        before = int(health.hp)
        after = max(0, before - amount)
        was_alive = bool(health.alive)

        health.hp = after
        health.alive = after > 0

        spawned.append(
            Event(
                type=HP_CHANGED,
                actor=event.actor,
                target=event.target,
                data={
                    "source_id": event.actor,
                    "target_id": event.target,
                    "hp_before": before,
                    "hp_after": after,
                },
            )
        )

        if was_alive and after == 0:
            spawned.append(
                Event(
                    type=ENTITY_DIED,
                    actor=event.actor,
                    target=event.target,
                    data={
                        "source_id": event.actor,
                        "target_id": event.target,
                    },
                )
            )
        return spawned

    if event.type == HEAL_APPLIED and event.target:
        if not world.has_component(event.target, HealthComponent):
            return spawned

        health = world.get_component(event.target, HealthComponent)
        amount = _as_non_negative_int(event.data.get("amount", 0))

        before = int(health.hp)
        after = min(int(health.max_hp), before + amount)
        health.hp = after
        health.alive = after > 0

        if bool(event.data.get("consume_heal", False)) and event.actor and world.has_component(event.actor, HealProfileComponent):
            heals = world.get_component(event.actor, HealProfileComponent)
            heals.heals_remaining = max(0, int(heals.heals_remaining) - 1)

        spawned.append(
            Event(
                type=HP_CHANGED,
                actor=event.actor,
                target=event.target,
                data={
                    "source_id": event.actor,
                    "target_id": event.target,
                    "hp_before": before,
                    "hp_after": after,
                    "heals_remaining": _heals_remaining(world, event.actor),
                },
            )
        )
        return spawned

    if event.type == MOVED and event.target:
        distance = _as_int(event.data.get("distance", 0), default=0)

        if world.has_component(event.target, MovementComponent):
            move = world.get_component(event.target, MovementComponent)
            allowed = min(abs(distance), max(0, move.remaining))
            signed = allowed if distance >= 0 else -allowed
            move.remaining = max(0, move.remaining - allowed)
        else:
            signed = distance

        if world.has_component(event.target, PositionComponent):
            pos = world.get_component(event.target, PositionComponent)
            pos.x += signed
        else:
            world.add_component(event.target, PositionComponent(x=signed, y=0))

        return spawned

    if event.type == STATS_MODIFIED and event.target:
        bonuses_raw = event.data.get("bonuses")
        if not isinstance(bonuses_raw, dict):
            return spawned

        stats = world.try_component(event.target, StatsComponent)
        if stats is None:
            stats = StatsComponent()
            world.add_component(event.target, stats)

        for key, value in bonuses_raw.items():
            if not isinstance(key, str):
                continue
            delta = _as_int(value, default=0)
            match key:
                case "strength" | "str":
                    stats.strength += delta
                case "dexterity" | "dex":
                    stats.dexterity += delta
                case "constitution" | "con":
                    stats.constitution += delta
                case "intelligence" | "int":
                    stats.intelligence += delta
                case "wisdom" | "wis":
                    stats.wisdom += delta
                case "charisma" | "cha":
                    stats.charisma += delta
        return spawned

    return spawned


def _encounter(world: ECSRegistry, encounter_entity: str) -> EncounterComponent:
    if not world.has_component(encounter_entity, EncounterComponent):
        world.ensure_entity(encounter_entity)
        world.add_component(encounter_entity, EncounterComponent())
    return world.get_component(encounter_entity, EncounterComponent)


def _as_non_negative_int(value: object) -> int:
    n = _as_int(value, default=0)
    return max(0, n)


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _heals_remaining(world: ECSRegistry, actor_id: str | None) -> int:
    if not actor_id:
        return 0
    heals = world.try_component(actor_id, HealProfileComponent)
    if heals is None:
        return 0
    return int(heals.heals_remaining)
