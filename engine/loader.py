# engine/loader.py
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .models import AttackProfile, Combatant

JsonDict = Dict[str, Any]


@dataclass
class DbLoader:
    """
    Loader for the compiled codex DB.

    Expected schema (stable):
      - entities(id TEXT PRIMARY KEY, endpoint TEXT, api_index TEXT, name TEXT, json TEXT, ...)
      - index on (endpoint, api_index)

    This loader is intentionally strict: if the DB doesn't match the codex schema,
    we want to fail fast and fix the pipeline—not silently guess.
    """
    db_path: str

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _loads_json(value: Any) -> JsonDict:
        if isinstance(value, (bytes, bytearray)):
            return json.loads(value.decode("utf-8"))
        if isinstance(value, str):
            return json.loads(value)
        raise TypeError(f"Unsupported JSON column type: {type(value)}")

    def _assert_schema(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entities'")
        if cur.fetchone() is None:
            raise RuntimeError("Invalid codex DB: missing required table 'entities'.")

        cur.execute("PRAGMA table_info(entities)")
        cols = {row[1] for row in cur.fetchall()}  # row[1] = column name
        required = {"id", "endpoint", "api_index", "json"}
        missing = required - cols
        if missing:
            raise RuntimeError(f"Invalid codex DB: entities table missing columns: {sorted(missing)}")

    def get_json_by_id(self, entity_id: str) -> JsonDict:
        with self._connect() as conn:
            self._assert_schema(conn)
            cur = conn.cursor()
            cur.execute("SELECT json FROM entities WHERE id = ? LIMIT 1", (entity_id,))
            row = cur.fetchone()
            if not row or row[0] is None:
                raise KeyError(f"Entity not found: {entity_id!r}")
            return self._loads_json(row[0])

    def get_entity_json(self, endpoint: str, api_index: str) -> JsonDict:
        entity_id = f"{endpoint}:{api_index}"
        try:
            return self.get_json_by_id(entity_id)
        except KeyError:
            # fallback: query by endpoint/index (same result, helps debugging if ids differ)
            with self._connect() as conn:
                self._assert_schema(conn)
                cur = conn.cursor()
                cur.execute(
                    "SELECT json FROM entities WHERE endpoint = ? AND api_index = ? LIMIT 1",
                    (endpoint, api_index),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    raise KeyError(f"Entity not found: endpoint={endpoint!r}, api_index={api_index!r}")
                return self._loads_json(row[0])

    @staticmethod
    def _parse_ac(raw: Any, name: str) -> int:
        if isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, dict) and "value" in first:
                return int(first["value"])
            if isinstance(first, int):
                return int(first)
            raise ValueError(f"Unsupported armor_class entry for {name!r}: {first!r}")

        if isinstance(raw, int):
            return int(raw)

        raise ValueError(f"Missing/invalid armor_class for {name!r}: {raw!r}")

    @staticmethod
    def _extract_attacks(raw: JsonDict) -> List[AttackProfile]:
        attacks: List[AttackProfile] = []
        for a in raw.get("actions", []):
            if not isinstance(a, dict):
                continue
            if "attack_bonus" not in a:
                continue

            dmg_list = a.get("damage") or []
            if not isinstance(dmg_list, list) or not dmg_list:
                continue

            dmg0 = None
            for entry in dmg_list:
                if isinstance(entry, dict) and isinstance(entry.get("damage_dice"), str) and entry["damage_dice"].strip():
                    dmg0 = entry
                    break
            if dmg0 is None:
                continue

            damage_dice = dmg0["damage_dice"].strip()
            damage_type = (dmg0.get("damage_type") or {}).get("name", "Unknown")

            attacks.append(
                AttackProfile(
                    name=str(a.get("name", "Attack")),
                    attack_bonus=int(a["attack_bonus"]),
                    damage_dice=damage_dice,
                    damage_type=str(damage_type),
                )
            )

        return attacks

    def load_monster_combatant(
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
        raw = self.get_entity_json("monsters", api_index)

        name = str(raw["name"])
        ac = ac_override if ac_override is not None else self._parse_ac(raw.get("armor_class"), name=name)

        max_hp = int(raw["hit_points"])
        if max_hp_override is not None:
            max_hp = int(max_hp_override)

        dex = int(raw["dexterity"])

        attacks = self._extract_attacks(raw)
        if not attacks:
            raise ValueError(f"Monster {name!r} has no usable attacks in DB payload.")

        idx = str(raw.get("index", api_index))
        cid = instance_id if instance_id is not None else f"{team}:{idx}"

        return Combatant(
            id=cid,
            name=name,
            team=team,
            ac=ac,
            max_hp=max_hp,
            hp=max_hp,
            dex=dex,
            attacks=attacks,
            heals_remaining=heals_remaining,
            heal_dice=heal_dice,
        )