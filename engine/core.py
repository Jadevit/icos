# engine/core.py
from __future__ import annotations

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
from .encounter import Encounter

from .content.bundles import bundle_pack
from .content.codex import (
    bundle_name_for_pack,
    compute_codex_checksum,
    merge_codex,
    read_codex_manifest,
)

EventSink = Callable[[Event], None]


@dataclass
class IcosEngine:
    """
    IcosEngine is the façade / public API for the engine.

    Everything external (CLI, tests, future UI, mod tools) should call into this
    instead of wiring internal modules together ad hoc.
    """

    paths: EnginePaths = field(default_factory=EnginePaths)
    seed: Optional[int] = None

    dice: Dice = field(init=False)
    loader: DbLoader = field(init=False)
    registry: ActionRegistry = field(init=False)

    def __post_init__(self) -> None:
        self.dice = Dice(seed=self.seed) if self.seed is not None else Dice()
        self.registry = ActionRegistry()
        self.loader = DbLoader(db_path=str(self.paths.abs(self.paths.codex_db)))

    # --- Content pipeline -------------------------------------------------

    def ensure_codex(self) -> None:
        """
        Ensure bundles + codex.db exist and are up to date.

        Current behavior:
          - builds/overwrites pack bundle DBs
          - computes a codex checksum from bundle hashes + load order
          - skips codex merge if checksum matches and codex.db already exists
        """
        manifest_path = self.paths.abs(self.paths.codex_manifest)
        bundles_dir = self.paths.abs(self.paths.bundles_dir)
        codex_db = self.paths.abs(self.paths.codex_db)
        checksum_path = self.paths.abs(self.paths.codex_checksum)

        bundles_dir.mkdir(parents=True, exist_ok=True)
        codex_db.parent.mkdir(parents=True, exist_ok=True)

        # Manifest stores pack paths relative to repo root (ex: data/content/base)
        pack_paths = [Path(p) for p in read_codex_manifest(manifest_path)]
        pack_roots = [self.paths.abs(p) for p in pack_paths]

        # 1) Build/refresh per-pack bundles
        # (Simple + reliable. Later we can skip per-pack rebuilds based on pack hash.)
        for pack_root in pack_roots:
            out_db = bundles_dir / bundle_name_for_pack(pack_root)
            bundle_pack(pack_root, out_db)

        # 2) Compute checksum (order + bundle hashes)
        new_checksum = compute_codex_checksum(pack_roots, bundles_dir)

        old_checksum = ""
        if checksum_path.exists():
            old_checksum = checksum_path.read_text(encoding="utf-8").strip()

        # Skip expensive merge if nothing changed
        if codex_db.exists() and old_checksum == new_checksum:
            return

        merge_codex(pack_roots, bundles_dir, codex_db)
        checksum_path.write_text(new_checksum + "\n", encoding="utf-8")

    # --- Spawn helpers ----------------------------------------------------

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
        """
        Convenience wrapper around DbLoader -> Combatant conversion.
        """
        return self.loader.load_monster_combatant(
            api_index,
            team=team,
            instance_id=instance_id,
            max_hp_override=max_hp_override,
            ac_override=ac_override,
            heals_remaining=heals_remaining,
            heal_dice=heal_dice,
        )

    # --- Combat -----------------------------------------------------------

    def encounter(self, *, max_rounds: int = 50, on_event: Optional[EventSink] = None) -> Encounter:
        """
        Create an Encounter builder preconfigured with engine-friendly defaults.
        """
        return Encounter(max_rounds=max_rounds, on_event=on_event)

    def run_encounter(
        self,
        enc: Encounter,
        *,
        max_rounds: Optional[int] = None,
        on_event: Optional[EventSink] = None,
    ) -> list[Event]:
        """
        Run an Encounter. Convenience wrapper around run_combat().
        """
        return self.run_combat(
            enc.combatants,
            controllers=enc.controllers,
            max_rounds=max_rounds if max_rounds is not None else enc.max_rounds,
            on_event=on_event if on_event is not None else enc.on_event,
        )
    
    def run_combat(
        self,
        combatants: list[Combatant],
        controllers: Mapping[str, CombatController],
        *,
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
    ) -> list[Event]:
        """
        Run a combat encounter. No assumptions about 1v1 vs teams.

        Controllers decide actions; RulesEngine resolves; events are streamed to on_event.
        """
        session = CombatSession(dice=self.dice)
        return session.run(
            combatants,
            controllers=controllers,
            max_rounds=max_rounds,
            on_event=on_event,
        )