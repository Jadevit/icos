from __future__ import annotations

from typing import Any, Iterable

from icos.content.defs.common import DamageSpec, ResourceRef
from icos.content.defs.spell import SpellDefinition

from .base import EntityCompiler, EntityRecord


class SpellCompiler(EntityCompiler[SpellDefinition]):
    endpoint = "spells"

    def compile(self, record: EntityRecord) -> SpellDefinition:
        raw = dict(record.json)
        damage = raw.get("damage")

        return SpellDefinition(
            id=record.id,
            endpoint=record.endpoint,
            api_index=record.api_index,
            name=_as_str(raw.get("name"), fallback=record.name),
            level=_as_int(raw.get("level"), default=0),
            school=_parse_ref(raw.get("school")),
            casting_time=_as_str(raw.get("casting_time")),
            range=_as_str(raw.get("range")),
            duration=_as_str(raw.get("duration")),
            concentration=bool(raw.get("concentration")),
            ritual=bool(raw.get("ritual")),
            components=tuple(_parse_components(raw.get("components"))),
            material=_as_str(raw.get("material")),
            desc=tuple(_parse_text_list(raw.get("desc"))),
            higher_level=tuple(_parse_text_list(raw.get("higher_level"))),
            attack_type=_as_str(raw.get("attack_type")),
            damage_at_slot_level=_parse_str_map(
                damage.get("damage_at_slot_level") if isinstance(damage, dict) else None
            ),
            damage_at_character_level=_parse_str_map(
                damage.get("damage_at_character_level") if isinstance(damage, dict) else None
            ),
            damage=tuple(_parse_damage_entries(damage.get("damage_type") if isinstance(damage, dict) else None)),
            classes=tuple(_parse_ref_seq(raw.get("classes"))),
            subclasses=tuple(_parse_ref_seq(raw.get("subclasses"))),
            url=_as_str(raw.get("url")),
            raw_json=raw,
        )


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


def _parse_components(values: Any) -> Iterable[str]:
    if not isinstance(values, list):
        return ()
    return [_as_str(v) for v in values if isinstance(v, (str, int, float))]


def _parse_text_list(values: Any) -> Iterable[str]:
    if isinstance(values, str):
        return (values,)
    if not isinstance(values, list):
        return ()
    return [_as_str(v) for v in values if isinstance(v, (str, int, float))]


def _parse_str_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, val in value.items():
        if isinstance(key, str):
            out[key] = _as_str(val)
    return out


def _parse_damage_entries(raw_damage_type: Any) -> Iterable[DamageSpec]:
    if raw_damage_type is None:
        return ()
    ref = _parse_ref(raw_damage_type)
    if ref is None:
        return ()
    return (DamageSpec(damage_dice="", damage_type=ref),)
