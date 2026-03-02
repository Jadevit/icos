from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, TypeVar, cast

from icos.content.compilers.base import EntityRecord
from icos.content.compilers.conditions import ConditionCompiler
from icos.content.compilers.creatures import MonsterCompiler
from icos.content.compilers.generic import GenericCompiler
from icos.content.compilers.items import EquipmentCompiler
from icos.content.compilers.registry import CompilerRegistry
from icos.content.compilers.spells import SpellCompiler
from icos.content.db import CodexDb, EntityRow
from icos.content.defs.condition import ConditionDefinition
from icos.content.defs.creature import MonsterDefinition
from icos.content.defs.entity import GenericEntityDefinition
from icos.content.defs.item import EquipmentDefinition
from icos.content.defs.spell import SpellDefinition

T = TypeVar("T")


@dataclass
class ContentStore:
    db: CodexDb
    registry: CompilerRegistry = field(default_factory=CompilerRegistry)
    _cache: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.registry.endpoints():
            self.registry.register(MonsterCompiler())
            self.registry.register(EquipmentCompiler())
            self.registry.register(SpellCompiler())
            self.registry.register(ConditionCompiler())
            for endpoint in self.db.list_endpoints():
                if not self.registry.has(endpoint):
                    self.registry.register(GenericCompiler(endpoint=endpoint))

    def get_compiled(self, endpoint: str, api_index: str) -> Any:
        entity_id = f"{endpoint}:{api_index}"
        cached = self._cache.get(entity_id)
        if cached is not None:
            return cached

        row = self.db.get_row(endpoint, api_index)
        compiled = self._compile_row(row)
        self._cache[entity_id] = compiled
        return compiled

    def list_compiled(self, endpoint: str, *, limit: int | None = None) -> List[Any]:
        out: List[Any] = []
        for row in self.db.iter_endpoint(endpoint, limit=limit):
            if row.id in self._cache:
                out.append(self._cache[row.id])
                continue
            compiled = self._compile_row(row)
            self._cache[row.id] = compiled
            out.append(compiled)
        return out

    def list_endpoints(self) -> List[str]:
        return list(self.db.list_endpoints())

    def count_by_endpoint(self) -> Dict[str, int]:
        return self.db.count_by_endpoint()

    def get_monster(self, api_index: str) -> MonsterDefinition:
        return cast(MonsterDefinition, self.get_compiled("monsters", api_index))

    def list_monsters(self, *, limit: int | None = None) -> List[MonsterDefinition]:
        return cast(List[MonsterDefinition], self.list_compiled("monsters", limit=limit))

    def get_equipment(self, api_index: str) -> EquipmentDefinition:
        return cast(EquipmentDefinition, self.get_compiled("equipment", api_index))

    def list_equipment(self, *, limit: int | None = None) -> List[EquipmentDefinition]:
        return cast(List[EquipmentDefinition], self.list_compiled("equipment", limit=limit))

    def get_spell(self, api_index: str) -> SpellDefinition:
        return cast(SpellDefinition, self.get_compiled("spells", api_index))

    def list_spells(self, *, limit: int | None = None) -> List[SpellDefinition]:
        return cast(List[SpellDefinition], self.list_compiled("spells", limit=limit))

    def get_condition(self, api_index: str) -> ConditionDefinition:
        return cast(ConditionDefinition, self.get_compiled("conditions", api_index))

    def list_conditions(self, *, limit: int | None = None) -> List[ConditionDefinition]:
        return cast(List[ConditionDefinition], self.list_compiled("conditions", limit=limit))

    def get_generic(self, endpoint: str, api_index: str) -> GenericEntityDefinition:
        return cast(GenericEntityDefinition, self.get_compiled(endpoint, api_index))

    @staticmethod
    def _to_record(row: EntityRow) -> EntityRecord:
        return EntityRecord(
            id=row.id,
            endpoint=row.endpoint,
            api_index=row.api_index,
            name=row.name,
            json=row.json,
        )

    def _compile_row(self, row: EntityRow) -> Any:
        compiler = self.registry.resolve(row.endpoint)
        return compiler.compile(self._to_record(row))
