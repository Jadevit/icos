# engine/core.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

from .config import EnginePaths
from .dice import Dice
from .loader import DbLoader
from .models import Combatant, Event
from .session import CombatSession
from .systems.actions.registry import ActionRegistry
from .systems.ai.interface import CombatController
from .content.bundles import bundle_pack, default_bundle_name
from .content.codex import merge_codex, read_codex_manifest


EventSink = Callable[[Event], None]


@dataclass
class IcosEngine:
    """
    The Icos Engine façade.

    This is the stable API that CLI/tools/future UI/mod tools should call.
    """
    paths: EnginePaths = field(default_factory=EnginePaths)
    seed: Optional[int] = None

    dice: Dice = field(init=False)
    loader: DbLoader = field(init=False)
    registry: ActionRegistry = field(init=False)

    def __post_init__(self) -> None:
        self.dice = Dice(seed=self.seed) if self.seed is not None else Dice()
        self.registry = ActionRegistry()
        # loader path points at the compiled codex DB
        self.loader = DbLoader(db_path=str(self.paths.abs(self.paths.codex_db)))

    # --- Content pipeline -----------------------------------------

    def ensure_codex(self) -> None:
        """
        Ensure per-pack bundles exist and codex.db is built.
        For now: always rebuild if codex.db missing.
        Next step: compare checksums/hashes and skip when unchanged.
        """
        codex_db = self.paths.abs(self.paths.codex_db)
        manifest_path = self.paths.abs(self.paths.codex_manifest)
        bundles_dir = self.paths.abs(self.paths.bundles_dir)

        bundles_dir.mkdir(parents=True, exist_ok=True)
        codex_db.parent.mkdir(parents=True, exist_ok=True)

        pack_paths = [Path(p) for p in read_codex_manifest(manifest_path)]

        # 1) build each pack bundle
        for pack_root in pack_paths:
            pack_root_abs = self.paths.abs(pack_root)
            out_db = bundles_dir / default_bundle_name(pack_root_abs)
            bundle_pack(pack_root_abs, out_db)

        # 2) merge into final codex
        merge_codex([self.paths.abs(p) for p in pack_paths], bundles_dir, codex_db)

    # --- Encounter helpers ----------------------------------------

    def spawn_monster(
        self,
        api_index: str,
        *,
        team: str = "enemies",
        instance_id: Optional[str] = None,
        max_hp_override: Optional[int] = None,
        ac_override: Optional[int] = None,
        heals_remaining: int = 0,
        heal_dice: str = "1d8+2",
    ) -> Combatant:
        return self.loader.load_monster_combatant(
            api_index,
            team=team,
            instance_id=instance_id,
            max_hp_override=max_hp_override,
            ac_override=ac_override,
            heals_remaining=heals_remaining,
            heal_dice=heal_dice,
        )

    def run_combat(
        self,
        combatants: list[Combatant],
        controllers: Mapping[str, CombatController],
        *,
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
    ) -> list[Event]:
        session = CombatSession(dice=self.dice)
        return session.run(combatants, controllers=controllers, max_rounds=max_rounds, on_event=on_event)