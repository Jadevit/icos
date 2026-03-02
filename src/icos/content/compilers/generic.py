from __future__ import annotations

from typing import Any, Iterable

from icos.content.defs.entity import GenericEntityDefinition

from .base import EntityCompiler, EntityRecord


class GenericCompiler(EntityCompiler[GenericEntityDefinition]):
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def compile(self, record: EntityRecord) -> GenericEntityDefinition:
        raw = dict(record.json)
        return GenericEntityDefinition(
            id=record.id,
            endpoint=record.endpoint,
            api_index=record.api_index,
            name=_as_str(raw.get("name"), fallback=record.name or record.api_index),
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
    for item in raw:
        if isinstance(item, (str, int, float)):
            out.append(str(item))
    return out
