from __future__ import annotations

from typing import Any, Iterable

from icos.content.defs.common import ResourceRef
from icos.content.defs.item import EquipmentDefinition

from .base import EntityCompiler, EntityRecord


class EquipmentCompiler(EntityCompiler[EquipmentDefinition]):
    endpoint = "equipment"

    def compile(self, record: EntityRecord) -> EquipmentDefinition:
        raw = dict(record.json)
        armor_class = raw.get("armor_class")
        damage = raw.get("damage")
        cost = raw.get("cost")

        return EquipmentDefinition(
            id=record.id,
            endpoint=record.endpoint,
            api_index=record.api_index,
            name=_as_str(raw.get("name"), fallback=record.name),
            equipment_category=_parse_ref(raw.get("equipment_category")),
            gear_category=_parse_ref(raw.get("gear_category")),
            armor_category=_as_str(raw.get("armor_category")),
            weapon_category=_as_str(raw.get("weapon_category")),
            weapon_range=_as_str(raw.get("weapon_range")),
            cost_quantity=_as_int(cost.get("quantity") if isinstance(cost, dict) else None, default=0),
            cost_unit=_as_str(cost.get("unit") if isinstance(cost, dict) else None),
            weight=_as_float(raw.get("weight"), default=0.0),
            damage_dice=_as_str(damage.get("damage_dice") if isinstance(damage, dict) else None),
            damage_type=_parse_ref(damage.get("damage_type") if isinstance(damage, dict) else None),
            armor_class_base=_as_int(armor_class.get("base") if isinstance(armor_class, dict) else None, default=0),
            armor_class_dex_bonus=bool(armor_class.get("dex_bonus")) if isinstance(armor_class, dict) else False,
            armor_class_max_bonus=_as_int_or_none(armor_class.get("max_bonus")) if isinstance(armor_class, dict) else None,
            properties=tuple(_parse_ref_seq(raw.get("properties"))),
            desc=tuple(_parse_desc(raw.get("desc"))),
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


def _as_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
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


def _parse_desc(raw: Any) -> Iterable[str]:
    if isinstance(raw, str):
        return (raw,)
    if not isinstance(raw, list):
        return ()
    return [_as_str(v) for v in raw if isinstance(v, (str, int, float))]
