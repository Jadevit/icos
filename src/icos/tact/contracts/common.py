from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def to_json_value(value: Any) -> JsonValue:
    """
    Convert runtime objects into JSON-safe deterministic values.

    Unsupported objects are stringified explicitly to avoid silent drop.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, tuple):
        return [to_json_value(v) for v in value]

    if isinstance(value, list):
        return [to_json_value(v) for v in value]

    if isinstance(value, Mapping):
        out: dict[str, JsonValue] = {}
        for k in sorted(value.keys(), key=lambda x: str(x)):
            out[str(k)] = to_json_value(value[k])
        return out

    if is_dataclass(value):
        return to_json_value(asdict(value))

    if hasattr(value, "__dict__"):
        return to_json_value(vars(value))

    return str(value)


def to_json_dict(value: Any) -> dict[str, JsonValue]:
    """
    Convert any value into a JSON-safe dictionary payload.

    Dataclasses are flattened via ``asdict``; non-dicts are wrapped into ``{"value": ...}``.
    """
    raw = to_json_value(value)
    if isinstance(raw, dict):
        return raw
    return {"value": raw}
