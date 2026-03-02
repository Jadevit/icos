from __future__ import annotations

from typing import Any, Iterable

from icos.content.defs.common import (
    AbilityScores,
    ActionTextBlock,
    ArmorClassEntry,
    DamageSpec,
    ResourceRef,
    SpeedProfile,
)
from icos.content.defs.creature import MonsterAction, MonsterDefinition

from .base import EntityCompiler, EntityRecord


class MonsterCompiler(EntityCompiler[MonsterDefinition]):
    endpoint = "monsters"

    def compile(self, record: EntityRecord) -> MonsterDefinition:
        raw = dict(record.json)
        return MonsterDefinition(
            id=record.id,
            endpoint=record.endpoint,
            api_index=record.api_index,
            name=_as_str(raw.get("name"), fallback=record.name),
            creature_type=_as_str(raw.get("type")),
            subtype=_as_str(raw.get("subtype")),
            size=_as_str(raw.get("size")),
            alignment=_as_str(raw.get("alignment")),
            languages=_as_str(raw.get("languages")),
            challenge_rating=_as_float(raw.get("challenge_rating"), default=0.0),
            xp=_as_int(raw.get("xp"), default=0),
            proficiency_bonus=_as_int(raw.get("proficiency_bonus"), default=0),
            armor_class=tuple(_parse_armor_class(raw.get("armor_class"))),
            hit_points=_as_int(raw.get("hit_points"), default=1),
            hit_dice=_as_str(raw.get("hit_dice")),
            hit_points_roll=_as_str(raw.get("hit_points_roll")),
            abilities=AbilityScores(
                strength=_as_int(raw.get("strength"), default=10),
                dexterity=_as_int(raw.get("dexterity"), default=10),
                constitution=_as_int(raw.get("constitution"), default=10),
                intelligence=_as_int(raw.get("intelligence"), default=10),
                wisdom=_as_int(raw.get("wisdom"), default=10),
                charisma=_as_int(raw.get("charisma"), default=10),
            ),
            speed=SpeedProfile(values=_parse_speed(raw.get("speed"))),
            senses=_parse_dict(raw.get("senses")),
            damage_immunities=tuple(_parse_str_seq(raw.get("damage_immunities"))),
            damage_resistances=tuple(_parse_str_seq(raw.get("damage_resistances"))),
            damage_vulnerabilities=tuple(_parse_str_seq(raw.get("damage_vulnerabilities"))),
            condition_immunities=tuple(_parse_ref_names(raw.get("condition_immunities"))),
            actions=tuple(_parse_monster_actions(raw.get("actions"))),
            special_abilities=tuple(_parse_action_text(raw.get("special_abilities"))),
            reactions=tuple(_parse_action_text(raw.get("reactions"))),
            legendary_actions=tuple(_parse_action_text(raw.get("legendary_actions"))),
            image=_as_str(raw.get("image")),
            url=_as_str(raw.get("url")),
            updated_at=_as_str(raw.get("updated_at")),
            raw_json=raw,
        )


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return fallback
    return str(value)


def _parse_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _parse_ref(value: Any) -> ResourceRef | None:
    if not isinstance(value, dict):
        return None
    index = value.get("index")
    name = value.get("name")
    if not isinstance(index, str) or not isinstance(name, str):
        return None
    url = value.get("url")
    return ResourceRef(index=index, name=name, url=url if isinstance(url, str) else "")


def _parse_ref_seq(values: Any) -> Iterable[ResourceRef]:
    if not isinstance(values, list):
        return ()
    out: list[ResourceRef] = []
    for value in values:
        ref = _parse_ref(value)
        if ref is not None:
            out.append(ref)
    return out


def _parse_ref_names(values: Any) -> Iterable[str]:
    if not isinstance(values, list):
        return ()

    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            out.append(value)
            continue
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            out.append(value["name"])
    return out


def _parse_str_seq(values: Any) -> Iterable[str]:
    if not isinstance(values, list):
        return ()
    return [str(v) for v in values if isinstance(v, (str, int, float))]


def _parse_speed(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str):
            out[key] = _as_str(value)
    return out


def _parse_armor_class(raw: Any) -> Iterable[ArmorClassEntry]:
    if isinstance(raw, int):
        return (ArmorClassEntry(value=raw),)
    if not isinstance(raw, list):
        return ()

    out: list[ArmorClassEntry] = []
    for entry in raw:
        if isinstance(entry, int):
            out.append(ArmorClassEntry(value=entry))
            continue

        if not isinstance(entry, dict):
            continue

        value = _as_int(entry.get("value"), default=0)
        if value <= 0:
            continue

        armor = tuple(_parse_ref_seq(entry.get("armor")))
        spell = _parse_ref(entry.get("spell"))

        out.append(
            ArmorClassEntry(
                value=value,
                ac_type=_as_str(entry.get("type")),
                armor=armor,
                condition=_as_str(entry.get("condition")),
                spell=spell,
            )
        )

    return out


def _parse_damage(raw: Any) -> Iterable[DamageSpec]:
    if not isinstance(raw, list):
        return ()

    out: list[DamageSpec] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        dice = _as_str(entry.get("damage_dice"))
        if not dice:
            continue

        out.append(DamageSpec(damage_dice=dice, damage_type=_parse_ref(entry.get("damage_type"))))

    return out


def _infer_attack_kind(desc: str) -> str:
    d = desc.lower()
    if d.startswith("melee"):
        return "melee"
    if d.startswith("ranged"):
        return "ranged"
    if "melee" in d and "attack" in d:
        return "melee"
    if "ranged" in d and "attack" in d:
        return "ranged"
    return ""


def _parse_action_text(raw: Any) -> Iterable[ActionTextBlock]:
    if not isinstance(raw, list):
        return ()

    out: list[ActionTextBlock] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = _as_str(entry.get("name"))
        desc = _as_str(entry.get("desc"))
        if name:
            out.append(ActionTextBlock(name=name, desc=desc))
    return out


def _parse_monster_actions(raw: Any) -> Iterable[MonsterAction]:
    if not isinstance(raw, list):
        return ()

    out: list[MonsterAction] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        name = _as_str(entry.get("name"))
        if not name:
            continue

        desc = _as_str(entry.get("desc"))
        attack_bonus = entry.get("attack_bonus")
        attack_bonus_num = _as_int(attack_bonus) if attack_bonus is not None else None

        nested_actions = tuple(_parse_action_text(entry.get("actions")))

        out.append(
            MonsterAction(
                name=name,
                desc=desc,
                attack_bonus=attack_bonus_num,
                attack_kind=_infer_attack_kind(desc),
                damages=tuple(_parse_damage(entry.get("damage"))),
                nested_actions=nested_actions,
            )
        )

    return out
