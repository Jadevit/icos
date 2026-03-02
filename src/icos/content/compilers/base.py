from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Mapping, Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class EntityRecord:
    id: str
    endpoint: str
    api_index: str
    name: str
    json: Mapping[str, Any]


class EntityCompiler(Protocol[T]):
    endpoint: str

    def compile(self, record: EntityRecord) -> T: ...
