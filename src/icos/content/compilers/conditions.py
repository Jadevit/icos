from __future__ import annotations

from typing import Any, Iterable

from icos.content.defs.condition import ConditionDefinition

from .base import EntityCompiler, EntityRecord


class ConditionCompiler(EntityCompiler[ConditionDefinition]):
    endpoint = "conditions"

    def compile(self, record: EntityRecord) -> ConditionDefinition:
        raw = dict(record.json)
        return ConditionDefinition(
            id=record.id,
            endpoint=record.endpoint,
            api_index=record.api_index,
            name=_as_str(raw.get("name"), fallback=record.name),
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


def _parse_desc(raw: Any) -> Iterable[str]:
    if isinstance(raw, str):
        return (raw,)
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for value in raw:
        if isinstance(value, (str, int, float)):
            out.append(str(value))
    return out
