from __future__ import annotations

from typing import Any, Iterable

from icos.content.defs.entity import GenericEntityDefinition
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


def ability_from_feature(defn: GenericEntityDefinition) -> AbilityDefinition | None:
    raw = defn.raw_json
    effects = tuple(_parse_effects(raw.get("effects")))
    if not effects:
        return None

    return AbilityDefinition(
        id=defn.id,
        name=defn.name,
        target_rule=_as_str(raw.get("target"), fallback="target"),
        range=_as_str(raw.get("range"), fallback="melee"),
        effects=effects,
    )


def _parse_effects(raw: Any) -> Iterable[EffectSpec]:
    if not isinstance(raw, list):
        return ()

    out: list[EffectSpec] = []
    for entry in raw:
        parsed = _parse_effect(entry)
        if parsed is not None:
            out.append(parsed)
    return out


def _parse_effect(raw: Any) -> EffectSpec | None:
    if not isinstance(raw, dict):
        return None

    effect_type = _as_str(raw.get("type")).strip().lower()
    target = _as_str(raw.get("target"), fallback="target")
    if not effect_type:
        return None

    if effect_type == "damage":
        amount = _as_str(raw.get("amount"))
        damage_type = _as_str(raw.get("damage_type"))
        if not amount or not damage_type:
            return None
        return DamageEffect(amount=amount, damage_type=damage_type, target=target)

    if effect_type == "heal":
        amount = _as_str(raw.get("amount"))
        if not amount:
            return None
        return HealEffect(amount=amount, target=target)

    if effect_type == "apply_condition":
        condition = _as_str(raw.get("condition")).strip().lower()
        if not condition:
            return None
        return ApplyConditionEffect(condition=condition, duration=max(1, _as_int(raw.get("duration"), default=1)), target=target)

    if effect_type == "move":
        return MoveEffect(distance=_as_int(raw.get("distance"), default=0), target=target)

    if effect_type == "modify_stat":
        return ModifyStatEffect(bonuses=_parse_bonuses(raw.get("bonuses")), target=target)

    if effect_type == "roll_check":
        stat = _as_str(raw.get("stat")).strip().lower()
        dc = _as_int(raw.get("dc"), default=0)
        if not stat or dc <= 0:
            return None
        return RollCheckEffect(
            stat=stat,
            dc=dc,
            target=target,
            bonus=_as_int(raw.get("bonus"), default=0),
            on_success=tuple(_parse_effects(raw.get("on_success"))),
            on_failure=tuple(_parse_effects(raw.get("on_failure"))),
        )

    return None


def _parse_bonuses(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        out[key] = _as_int(value, default=0)
    return out


def _as_str(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return fallback
    return str(value)


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
