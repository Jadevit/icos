from __future__ import annotations

from icos.game.ecs import ECSRegistry
from icos.game.effects import (
    AbilityDefinition,
    ApplyConditionEffect,
    DamageEffect,
    HealEffect,
    MoveEffect,
    RollCheckEffect,
    execute_ability,
)
from icos.game.events import ATTACK_STARTED, EventBus
from icos.game.rules.dice import Dice
from icos.tact.core.actions import ActionRequest
from icos.tact.events.types import Event

from .common import actor_snapshot


DISADVANTAGE_ATTACKER_CONDITIONS = {"poisoned", "blinded", "restrained"}
ADVANTAGE_DEFENDER_CONDITIONS = {"blinded", "restrained", "stunned", "paralyzed", "unconscious"}


def action_resolution_system(world: ECSRegistry, bus: EventBus, context: dict[str, object]) -> None:
    action = context.get("action")
    dice = context.get("dice")
    if not isinstance(action, ActionRequest):
        return
    if not isinstance(dice, Dice):
        raise TypeError("action_resolution_system requires Dice in context['dice']")

    actor = actor_snapshot(world, action.actor_id)
    if not actor.alive:
        return

    match action.action_id:
        case "attack":
            _resolve_attack(world=world, bus=bus, dice=dice, action=action)
        case "heal":
            _resolve_heal(world=world, bus=bus, dice=dice, action=action)
        case "defend":
            _resolve_defend(world=world, bus=bus, dice=dice, action=action)
        case "move":
            _resolve_move(world=world, bus=bus, dice=dice, action=action)
        case "use_ability" | "cast" | "ability":
            _resolve_external_ability(world=world, bus=bus, dice=dice, action=action, context=context)
        case "wait":
            bus.publish(
                Event(
                    type="wait",
                    actor=action.actor_id,
                    data={
                        "actor_id": action.actor_id,
                        "action_id": "wait",
                    },
                )
            )
        case _:
            raise ValueError(f"Unsupported action_id: {action.action_id!r}")


def _resolve_attack(*, world: ECSRegistry, bus: EventBus, dice: Dice, action: ActionRequest) -> None:
    attacker = actor_snapshot(world, action.actor_id)
    if not action.targets or not attacker.attacks:
        return

    target_id = str(action.targets[0])
    defender = actor_snapshot(world, target_id)
    if not defender.alive:
        return

    attack_index = int(action.data.get("attack_index", 0))
    if attack_index < 0 or attack_index >= len(attacker.attacks):
        attack_index = 0

    attack = attacker.attacks[attack_index]
    adv_state = _adv_state(attacker=attacker, defender=defender, attack_kind=attack.attack_kind)
    total_attack_bonus = int(attack.attack_bonus + attacker.attack_bonus_bonus)

    bus.publish(
        Event(
            type=ATTACK_STARTED,
            actor=attacker.id,
            target=defender.id,
            data={
                "actor_id": attacker.id,
                "target_id": defender.id,
                "attack_index": attack_index,
                "attack_kind": attack.attack_kind,
                "damage_dice": attack.damage_dice,
                "damage_type": attack.damage_type,
                "attack_bonus": total_attack_bonus,
                "adv_state": adv_state,
                "target_ac": defender.ac,
            },
        )
    )

    ability = AbilityDefinition(
        id=f"attack:{attack.name.lower().replace(' ', '_')}",
        name=attack.name,
        target_rule="target",
        range=attack.attack_kind,
        effects=(
            RollCheckEffect(
                stat="attack_bonus",
                dc=defender.ac,
                target="target",
                bonus=total_attack_bonus,
                on_success=(
                    DamageEffect(
                        amount=attack.damage_dice,
                        damage_type=attack.damage_type,
                        target="target",
                    ),
                ),
                on_failure=tuple(),
            ),
        ),
    )

    execute_ability(
        world=world,
        bus=bus,
        dice=dice,
        source_id=attacker.id,
        target_ids=[defender.id],
        ability=ability,
        context={
            "attack_bonus": total_attack_bonus,
            "adv_state": adv_state,
            "damage_bonus": attacker.damage_bonus_bonus,
        },
    )


def _resolve_heal(*, world: ECSRegistry, bus: EventBus, dice: Dice, action: ActionRequest) -> None:
    actor = actor_snapshot(world, action.actor_id)
    if actor.heals_remaining <= 0:
        bus.publish(
            Event(
                type="heal.failed",
                actor=actor.id,
                data={
                    "actor_id": actor.id,
                    "reason": "no_heals_remaining",
                    "heals_remaining": actor.heals_remaining,
                },
            )
        )
        return

    heal_dice = str(action.data.get("heal_dice", actor.heal_dice))
    ability = AbilityDefinition(
        id="ability:self_heal",
        name="Self Heal",
        target_rule="self",
        range="self",
        effects=(HealEffect(amount=heal_dice, target="self"),),
    )

    execute_ability(
        world=world,
        bus=bus,
        dice=dice,
        source_id=actor.id,
        target_ids=[actor.id],
        ability=ability,
        context={
            "heal_bonus": actor.heal_bonus_bonus,
            "consume_heal": True,
            "heal_dice": heal_dice,
        },
    )


def _resolve_defend(*, world: ECSRegistry, bus: EventBus, dice: Dice, action: ActionRequest) -> None:
    actor = actor_snapshot(world, action.actor_id)
    ability = AbilityDefinition(
        id="ability:defend",
        name="Defend",
        target_rule="self",
        range="self",
        effects=(ApplyConditionEffect(condition="defending", duration=1, target="self"),),
    )

    execute_ability(
        world=world,
        bus=bus,
        dice=dice,
        source_id=actor.id,
        target_ids=[actor.id],
        ability=ability,
        context={},
    )


def _resolve_move(*, world: ECSRegistry, bus: EventBus, dice: Dice, action: ActionRequest) -> None:
    actor = actor_snapshot(world, action.actor_id)
    raw = action.data.get("distance", 0)
    try:
        distance = int(raw)
    except (TypeError, ValueError):
        distance = 0

    if distance == 0:
        return

    ability = AbilityDefinition(
        id="ability:move",
        name="Move",
        target_rule="self",
        range="self",
        effects=(MoveEffect(distance=distance, target="self"),),
    )

    execute_ability(
        world=world,
        bus=bus,
        dice=dice,
        source_id=actor.id,
        target_ids=[actor.id],
        ability=ability,
        context={},
    )


def _resolve_external_ability(
    *,
    world: ECSRegistry,
    bus: EventBus,
    dice: Dice,
    action: ActionRequest,
    context: dict[str, object],
) -> None:
    catalog = context.get("ability_catalog")
    if not isinstance(catalog, dict):
        return

    ability_id = str(action.data.get("ability_id", "")).strip()
    if not ability_id:
        return

    ability = catalog.get(ability_id)
    if not isinstance(ability, AbilityDefinition):
        return

    targets = [str(t) for t in action.targets]
    execute_ability(
        world=world,
        bus=bus,
        dice=dice,
        source_id=action.actor_id,
        target_ids=targets,
        ability=ability,
        context={},
    )


def _adv_state(*, attacker, defender, attack_kind: str) -> str:
    adv = 0
    dis = 0

    if "defending" in defender.flags:
        dis += 1

    for condition in DISADVANTAGE_ATTACKER_CONDITIONS:
        if condition in attacker.conditions and attacker.conditions[condition] > 0:
            dis += 1

    for condition in ADVANTAGE_DEFENDER_CONDITIONS:
        if condition in defender.conditions and defender.conditions[condition] > 0:
            adv += 1

    if defender.conditions.get("prone", 0) > 0:
        if attack_kind == "ranged":
            dis += 1
        else:
            adv += 1

    if adv > 0 and dis == 0:
        return "adv"
    if dis > 0 and adv == 0:
        return "dis"
    return "normal"
