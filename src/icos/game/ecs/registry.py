from __future__ import annotations

from copy import deepcopy
from dataclasses import is_dataclass
from typing import Any, Iterator, TypeVar

from .components import EntityId

T = TypeVar("T")


class ECSRegistry:
    """Deterministic in-memory ECS registry with component-indexed storage."""

    def __init__(self) -> None:
        self._entities: list[EntityId] = []
        self._entity_set: set[EntityId] = set()
        self._next_entity_index: int = 1
        self._components: dict[type[Any], dict[EntityId, Any]] = {}

    def clone(self) -> "ECSRegistry":
        out = ECSRegistry()
        out._entities = list(self._entities)
        out._entity_set = set(self._entity_set)
        out._next_entity_index = self._next_entity_index
        out._components = deepcopy(self._components)
        return out

    def create_entity(self, entity_id: EntityId | None = None) -> EntityId:
        if entity_id is None:
            entity_id = f"entity:{self._next_entity_index:08d}"
            self._next_entity_index += 1

        if entity_id in self._entity_set:
            raise ValueError(f"Duplicate entity id: {entity_id}")

        self._entities.append(entity_id)
        self._entity_set.add(entity_id)
        return entity_id

    def ensure_entity(self, entity_id: EntityId) -> EntityId:
        if entity_id in self._entity_set:
            return entity_id
        return self.create_entity(entity_id)

    def has_entity(self, entity_id: EntityId) -> bool:
        return entity_id in self._entity_set

    def remove_entity(self, entity_id: EntityId) -> None:
        if entity_id not in self._entity_set:
            return

        self._entity_set.remove(entity_id)
        self._entities = [eid for eid in self._entities if eid != entity_id]
        for store in self._components.values():
            store.pop(entity_id, None)

    def entities(self) -> tuple[EntityId, ...]:
        return tuple(self._entities)

    def add_component(self, entity_id: EntityId, component: Any) -> None:
        if entity_id not in self._entity_set:
            raise KeyError(f"Unknown entity: {entity_id}")
        if not is_dataclass(component):
            raise TypeError("Components must be dataclass instances.")

        ctype = type(component)
        store = self._components.setdefault(ctype, {})
        store[entity_id] = component

    def has_component(self, entity_id: EntityId, ctype: type[T]) -> bool:
        return entity_id in self._components.get(ctype, {})

    def get_component(self, entity_id: EntityId, ctype: type[T]) -> T:
        try:
            return self._components[ctype][entity_id]
        except KeyError as exc:
            raise KeyError(f"Component {ctype.__name__} missing for entity {entity_id}") from exc

    def try_component(self, entity_id: EntityId, ctype: type[T]) -> T | None:
        return self._components.get(ctype, {}).get(entity_id)

    def remove_component(self, entity_id: EntityId, ctype: type[Any]) -> None:
        self._components.get(ctype, {}).pop(entity_id, None)

    def query_ids(self, *ctypes: type[Any]) -> list[EntityId]:
        if not ctypes:
            return list(self._entities)

        out: list[EntityId] = []
        for entity_id in self._entities:
            include = True
            for ctype in ctypes:
                if entity_id not in self._components.get(ctype, {}):
                    include = False
                    break
            if include:
                out.append(entity_id)
        return out

    def query(self, *ctypes: type[Any]) -> Iterator[tuple[Any, ...]]:
        for entity_id in self.query_ids(*ctypes):
            row: list[Any] = [entity_id]
            for ctype in ctypes:
                row.append(self._components[ctype][entity_id])
            yield tuple(row)
