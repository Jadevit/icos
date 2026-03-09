from __future__ import annotations

from typing import Iterable

from icos.content.defs.common import ability_mod
from icos.game.ecs import ECSRegistry, InventoryComponent, StatsComponent
from icos.game.events import (
    ABILITY_EFFECT_APPLIED,
    ABILITY_USED,
    CHECK_ROLLED,
    CONDITION_APPLIED,
    DAMAGE_APPLIED,
    HEAL_APPLIED,
    MOVED,
    STATS_MODIFIED,
    EventBus,
)
from icos.game.rules.dice import Dice
from icos.tact.events.types import Event

from .ability import AbilityDefinition
from .models import (
    ApplyConditionEffect,
    DamageEffect,
    EffectSpec,
    HealEffect,
    ModifyStatEffect,
    MoveEffect,
    RollCheckEffect,
)


def execute_ability(
    *,
    world: ECSRegistry,
    bus: EventBus,
    dice: Dice,
    source_id: str,
    target_ids: list[str],
    ability: AbilityDefinition,
    context: dict[str, object] | None = None,
) -> None:
    ctx = dict(context or {})
    bus.publish(
        Event(
            type=ABILITY_USED,
            actor=source_id,
            target=target_ids[0] if target_ids else None,
            data={
                "ability_id": ability.id,
                "source_id": source_id,
                "target_ids": list(target_ids),
            },
        )
    )

    for effect in ability.effects:
        _execute_effect(
            world=world,
            bus=bus,
            dice=dice,
            source_id=source_id,
            target_ids=target_ids,
            effect=effect,
            context=ctx,
        )


def _execute_effect(
    *,
    world: ECSRegistry,
    bus: EventBus,
    dice: Dice,
    source_id: str,
    target_ids: list[str],
    effect: EffectSpec,
    context: dict[str, object],
) -> None:
    targets = _resolve_targets(source_id=source_id, target_ids=target_ids, target_rule=getattr(effect, "target", "target"))
    if not targets and isinstance(effect, (HealEffect, MoveEffect, ModifyStatEffect)):
        targets = [source_id]

    if isinstance(effect, DamageEffect):
        for target_id in targets:
            crit = bool(context.get("critical_hit", False))
            amount = _resolve_amount(
                dice=dice,
                raw=effect.amount,
                critical=crit,
                critical_mode=str(context.get("critical_mode", "double_roll")),
            )
            damage_bonus = context.get("damage_bonus")
            if isinstance(damage_bonus, int):
                amount += int(damage_bonus)
            amount = max(0, amount)
            bus.publish(
                Event(
                    type=ABILITY_EFFECT_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "effect_type": "damage",
                        "ability_context": dict(context),
                    },
                )
            )
            bus.publish(
                Event(
                    type=DAMAGE_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "amount": amount,
                        "damage_type": effect.damage_type,
                        "crit": crit,
                    },
                )
            )
        return

    if isinstance(effect, HealEffect):
        for target_id in targets:
            amount = _resolve_amount(dice=dice, raw=effect.amount, critical=False, critical_mode="none")
            heal_bonus = context.get("heal_bonus")
            if isinstance(heal_bonus, int):
                amount += int(heal_bonus)
            amount = max(0, amount)
            bus.publish(
                Event(
                    type=ABILITY_EFFECT_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "effect_type": "heal",
                        "ability_context": dict(context),
                    },
                )
            )
            bus.publish(
                Event(
                    type=HEAL_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "amount": amount,
                        "consume_heal": bool(context.get("consume_heal", False)),
                        "heal_dice": str(context.get("heal_dice", effect.amount)),
                    },
                )
            )
        return

    if isinstance(effect, ApplyConditionEffect):
        for target_id in targets:
            bus.publish(
                Event(
                    type=ABILITY_EFFECT_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "effect_type": "apply_condition",
                        "ability_context": dict(context),
                    },
                )
            )
            bus.publish(
                Event(
                    type=CONDITION_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "condition": effect.condition,
                        "duration": max(1, effect.duration),
                    },
                )
            )
        return

    if isinstance(effect, MoveEffect):
        for target_id in targets:
            bus.publish(
                Event(
                    type=ABILITY_EFFECT_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "effect_type": "move",
                        "ability_context": dict(context),
                    },
                )
            )
            bus.publish(
                Event(
                    type=MOVED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "distance": int(effect.distance),
                    },
                )
            )
        return

    if isinstance(effect, ModifyStatEffect):
        for target_id in targets:
            bus.publish(
                Event(
                    type=ABILITY_EFFECT_APPLIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "effect_type": "modify_stat",
                        "ability_context": dict(context),
                    },
                )
            )
            bus.publish(
                Event(
                    type=STATS_MODIFIED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "bonuses": dict(effect.bonuses),
                    },
                )
            )
        return

    if isinstance(effect, RollCheckEffect):
        for target_id in targets:
            bonus = _resolve_check_bonus(
                world=world,
                source_id=source_id,
                target_id=target_id,
                stat=effect.stat,
                base_bonus=int(effect.bonus),
                context=context,
            )
            adv_state_raw = context.get("adv_state")
            adv_state = str(adv_state_raw) if isinstance(adv_state_raw, str) else "normal"
            natural, underlying = dice.d20_with_adv_state(adv_state)
            total = natural + bonus
            success = natural == 20 or total >= int(effect.dc)
            critical = bool(natural == 20 and effect.stat in {"attack", "attack_bonus"})

            context["last_check_success"] = success
            context["critical_hit"] = critical

            bus.publish(
                Event(
                    type=CHECK_ROLLED,
                    actor=source_id,
                    target=target_id,
                    data={
                        "source_id": source_id,
                        "target_id": target_id,
                        "stat": effect.stat,
                        "dc": int(effect.dc),
                        "natural": natural,
                        "underlying": list(underlying),
                        "adv_state": adv_state,
                        "bonus": bonus,
                        "total": total,
                        "success": success,
                        "critical": critical,
                    },
                )
            )

            branch = effect.on_success if success else effect.on_failure
            for branch_effect in branch:
                _execute_effect(
                    world=world,
                    bus=bus,
                    dice=dice,
                    source_id=source_id,
                    target_ids=[target_id],
                    effect=branch_effect,
                    context=context,
                )


def _resolve_targets(*, source_id: str, target_ids: list[str], target_rule: str) -> list[str]:
    rule = str(target_rule).strip().lower()
    if rule in {"self", "caster", "source"}:
        return [source_id]
    if rule in {"all", "all_targets"}:
        return list(target_ids)
    if rule in {"none", ""}:
        return []
    if target_ids:
        return [target_ids[0]]
    return []


def _resolve_amount(*, dice: Dice, raw: str, critical: bool, critical_mode: str) -> int:
    token = str(raw).strip()
    try:
        return int(token)
    except ValueError:
        if not critical:
            return max(0, dice.roll(token).total)

        mode = critical_mode.strip().lower()
        if mode in {"none", "off"}:
            return max(0, dice.roll(token).total)
        if mode == "double_total":
            return max(0, dice.roll(token).total * 2)

        # default: roll the full expression twice and sum for crit behavior.
        return max(0, dice.roll(token).total + dice.roll(token).total)


def _resolve_check_bonus(
    *,
    world: ECSRegistry,
    source_id: str,
    target_id: str,
    stat: str,
    base_bonus: int,
    context: dict[str, object],
) -> int:
    normalized = stat.strip().lower()
    if normalized in {"attack", "attack_bonus"}:
        attack_bonus = context.get("attack_bonus")
        if isinstance(attack_bonus, int):
            return attack_bonus
        return base_bonus

    stats_owner = source_id
    if normalized.startswith("target."):
        normalized = normalized.split(".", 1)[1]
        stats_owner = target_id

    stats = world.try_component(stats_owner, StatsComponent)
    inv = world.try_component(source_id, InventoryComponent)

    if stats is None:
        return base_bonus

    match normalized:
        case "str" | "strength":
            out = ability_mod(stats.strength)
        case "dex" | "dexterity":
            out = ability_mod(stats.dexterity)
        case "con" | "constitution":
            out = ability_mod(stats.constitution)
        case "int" | "intelligence":
            out = ability_mod(stats.intelligence)
        case "wis" | "wisdom":
            out = ability_mod(stats.wisdom)
        case "cha" | "charisma":
            out = ability_mod(stats.charisma)
        case _:
            out = 0

    if normalized in {"str", "strength", "dex", "dexterity"} and inv is not None:
        out += int(inv.attack_bonus)

    return out + base_bonus
