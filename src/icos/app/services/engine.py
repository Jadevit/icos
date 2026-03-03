from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generic, List, Mapping, Optional, TypeVar

from icos.kernel.api.engine import KernelEngine
from icos.kernel.core.session import EncounterController, EncounterLoop
from icos.kernel.core.types import ActorLike
from icos.kernel.events.types import Event
from icos.kernel.replay import ReplayFileV1, build_replay, write_replay

from icos.content.loader import CodexLoader
from icos.content.paths import ContentPaths
from icos.content.db import CodexDb
from icos.content.store import ContentStore
from icos.content.defs.condition import ConditionDefinition
from icos.content.defs.creature import MonsterDefinition
from icos.content.defs.entity import GenericEntityDefinition
from icos.content.defs.item import EquipmentDefinition
from icos.content.defs.spell import SpellDefinition
from icos.game.rules.dice import Dice
from icos.game.runtime.party import EncounterPlan
from icos.game.effects import AbilityDefinition, ability_from_feature

from icos.content.bundles import bundle_pack
from icos.content.codex import (
    bundle_name_for_pack,
    compute_codex_checksum,
    merge_codex,
    read_codex_manifest,
)

TActor = TypeVar("TActor", bound=ActorLike)
EventSink = Callable[[Event], None]


@dataclass
class GameEngine(Generic[TActor]):
    """
    Game-facing facade responsible for content compilation and integration with the turn engine.
    """
    paths: ContentPaths = field(default_factory=ContentPaths)
    seed: Optional[int] = None

    dice: Dice = field(init=False)
    loader: CodexLoader = field(init=False)
    db: CodexDb = field(init=False)
    content: ContentStore = field(init=False)
    kernel: KernelEngine[TActor] = field(default_factory=KernelEngine)

    def __post_init__(self) -> None:
        self.dice = Dice(seed=self.seed) if self.seed is not None else Dice()
        db_path = str(self.paths.abs(self.paths.codex_db))
        self.loader = CodexLoader(db_path=db_path)
        self.db = CodexDb(db_path=db_path)
        self.content = ContentStore(db=self.db)

    # --- Content pipeline -------------------------------------------------

    def ensure_codex(self) -> None:
        """
        Ensure bundles and codex.db exist and match the current enabled load order.
        """
        manifest_path = self.paths.abs(self.paths.codex_manifest)
        bundles_dir = self.paths.abs(self.paths.bundles_dir)
        codex_db = self.paths.abs(self.paths.codex_db)
        checksum_path = self.paths.abs(self.paths.codex_checksum)

        bundles_dir.mkdir(parents=True, exist_ok=True)
        codex_db.parent.mkdir(parents=True, exist_ok=True)

        pack_paths = [Path(p) for p in read_codex_manifest(manifest_path)]
        pack_roots = [self.paths.abs(p) for p in pack_paths]

        for pack_root in pack_roots:
            out_db = bundles_dir / bundle_name_for_pack(pack_root)
            bundle_pack(pack_root, out_db)

        new_checksum = compute_codex_checksum(pack_roots, bundles_dir)

        old_checksum = ""
        if checksum_path.exists():
            old_checksum = checksum_path.read_text(encoding="utf-8").strip()

        if codex_db.exists() and old_checksum == new_checksum:
            return

        merge_codex(pack_roots, bundles_dir, codex_db)
        checksum_path.write_text(new_checksum + "\n", encoding="utf-8")

    # --- Generic content access ------------------------------------------

    def get_json_by_id(self, entity_id: str) -> dict:
        return self.loader.get_json_by_id(entity_id)

    def get_entity_json(self, endpoint: str, api_index: str) -> dict:
        return self.loader.get_entity_json(endpoint, api_index)

    def get_entity(self, endpoint: str, api_index: str) -> object:
        return self.content.get_compiled(endpoint, api_index)

    def list_entities(self, endpoint: str, *, limit: int | None = None) -> list[object]:
        return self.content.list_compiled(endpoint, limit=limit)

    def list_endpoints(self) -> list[str]:
        return self.content.list_endpoints()

    def count_entities_by_endpoint(self) -> dict[str, int]:
        return self.content.count_by_endpoint()

    def get_monster(self, api_index: str) -> MonsterDefinition:
        return self.content.get_monster(api_index)

    def list_monsters(self, *, limit: int | None = None) -> list[MonsterDefinition]:
        return self.content.list_monsters(limit=limit)

    def get_equipment(self, api_index: str) -> EquipmentDefinition:
        return self.content.get_equipment(api_index)

    def list_equipment(self, *, limit: int | None = None) -> list[EquipmentDefinition]:
        return self.content.list_equipment(limit=limit)

    def get_spell(self, api_index: str) -> SpellDefinition:
        return self.content.get_spell(api_index)

    def list_spells(self, *, limit: int | None = None) -> list[SpellDefinition]:
        return self.content.list_spells(limit=limit)

    def get_condition(self, api_index: str) -> ConditionDefinition:
        return self.content.get_condition(api_index)

    def list_conditions(self, *, limit: int | None = None) -> list[ConditionDefinition]:
        return self.content.list_conditions(limit=limit)

    def get_generic(self, endpoint: str, api_index: str) -> GenericEntityDefinition:
        return self.content.get_generic(endpoint, api_index)

    # --- Encounter runner -------------------------------------------------

    def encounter(
        self,
        *,
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
    ) -> EncounterPlan[TActor]:
        return EncounterPlan(max_rounds=max_rounds, on_event=on_event)

    def run_encounter(
        self,
        *,
        loop: EncounterLoop[TActor],
        actors: List[TActor],
        controllers: Mapping[str, EncounterController[TActor]],
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
        replay_out: str | Path | None = None,
        replay_metadata: Optional[dict[str, Any]] = None,
    ) -> List[Event]:
        self._inject_ability_catalog(loop)
        events = self.kernel.run(
            loop=loop,
            actors=actors,
            controllers=controllers,
            max_rounds=max_rounds,
            on_event=on_event,
        )
        if replay_out is not None:
            metadata: dict[str, Any] = {
                "seed": self.seed,
                "max_rounds": max_rounds,
                "loop": type(loop).__name__,
            }
            if replay_metadata:
                metadata.update(replay_metadata)
            replay = self.build_replay(actors=actors, events=events, metadata=metadata)
            write_replay(replay_out, replay)
        return events

    def build_replay(
        self,
        *,
        actors: List[TActor],
        events: List[Event],
        metadata: Optional[dict[str, Any]] = None,
    ) -> ReplayFileV1:
        return build_replay(actors=actors, events=events, metadata=metadata)

    def _inject_ability_catalog(self, loop: EncounterLoop[TActor]) -> None:
        setter = getattr(loop, "set_ability_catalog", None)
        if not callable(setter):
            return
        setter(self._build_ability_catalog())

    def _build_ability_catalog(self) -> dict[str, AbilityDefinition]:
        out: dict[str, AbilityDefinition] = {}
        try:
            features = self.content.list_compiled("features")
        except Exception:
            return out

        for entry in features:
            if not isinstance(entry, GenericEntityDefinition):
                continue
            try:
                ability = ability_from_feature(entry)
            except Exception:
                continue
            if ability is None:
                continue
            out[entry.api_index] = ability
            out[entry.id] = ability

        return out
