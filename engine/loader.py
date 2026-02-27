# engine/loader.py
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import AttackProfile, Combatant


JsonDict = Dict[str, Any]


@dataclass
class DbLoader:
    db_path: str

    # Detected mapping
    _table: Optional[str] = None
    _json_col: Optional[str] = None
    _endpoint_col: Optional[str] = None
    _api_index_col: Optional[str] = None
    _id_col: Optional[str] = None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _list_tables(self, conn: sqlite3.Connection) -> List[str]:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [r[0] for r in cur.fetchall()]

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> List[str]:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        # rows: cid, name, type, notnull, dflt_value, pk
        return [r[1] for r in cur.fetchall()]

    @staticmethod
    def _pick_json_col(cols: Sequence[str]) -> Optional[str]:
        # Strong preference order
        preferred = ("json", "data", "payload", "blob")
        lower_map = {c.lower(): c for c in cols}

        for key in preferred:
            if key in lower_map:
                return lower_map[key]

        # Fallback: contains json/data
        for c in cols:
            lc = c.lower()
            if "json" in lc or "data" in lc:
                return c

        return None

    @staticmethod
    def _find_col(cols: Sequence[str], names: Sequence[str]) -> Optional[str]:
        lower_map = {c.lower(): c for c in cols}
        for n in names:
            if n in lower_map:
                return lower_map[n]
        return None

    def _detect_storage(self, conn: sqlite3.Connection) -> None:
        """
        Find the table/columns that hold SRD-ish JSON blobs.
        Supports schemas like:
          - entity(endpoint, api_index, json)
          - entities(endpoint, index, data/json)
          - records(id, json)
          - anything with a JSON/text column plus an identifier scheme
        """
        tables = self._list_tables(conn)
        if not tables:
            raise RuntimeError("No tables found in DB.")

        best: Optional[Tuple[int, str, str, Optional[str], Optional[str], Optional[str]]] = None
        # score, table, json_col, endpoint_col, api_index_col, id_col

        for t in tables:
            cols = self._table_columns(conn, t)

            json_col = self._pick_json_col(cols)
            if not json_col:
                continue

            endpoint_col = self._find_col(cols, ("endpoint", "category", "resource"))
            api_index_col = self._find_col(cols, ("api_index", "index", "slug", "key", "name_index"))
            id_col = self._find_col(cols, ("id", "uid", "entity_id"))

            score = 3  # json_col exists
            if endpoint_col:
                score += 3
            if api_index_col:
                score += 3
            if id_col:
                score += 2
            if t.lower() in ("entity", "entities"):
                score += 1

            candidate = (score, t, json_col, endpoint_col, api_index_col, id_col)
            if best is None or candidate[0] > best[0]:
                best = candidate

        if best is None:
            raise RuntimeError("Could not detect JSON storage table. Expected a table with a json/data column.")

        _, self._table, self._json_col, self._endpoint_col, self._api_index_col, self._id_col = best

    def _ensure_detected(self, conn: sqlite3.Connection) -> None:
        if self._table is None or self._json_col is None:
            self._detect_storage(conn)

    @staticmethod
    def _loads_json(value: Any) -> JsonDict:
        if isinstance(value, (bytes, bytearray)):
            return json.loads(value.decode("utf-8"))
        if isinstance(value, str):
            return json.loads(value)
        raise TypeError(f"Unsupported JSON column type: {type(value)}")

    def get_entity_json(self, endpoint: str, api_index: str) -> JsonDict:
        with self._connect() as conn:
            self._ensure_detected(conn)
            assert self._table and self._json_col

            cur = conn.cursor()

            # Attempt 1: endpoint + api_index style
            if self._endpoint_col and self._api_index_col:
                cur.execute(
                    f"""
                    SELECT {self._json_col}
                    FROM {self._table}
                    WHERE {self._endpoint_col} = ? AND {self._api_index_col} = ?
                    LIMIT 1
                    """,
                    (endpoint, api_index),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return self._loads_json(row[0])

            # Attempt 2: id-style like "monsters:goblin"
            if self._id_col:
                id_variants = (
                    f"{endpoint}:{api_index}",
                    f"/api/{endpoint}/{api_index}",
                    f"{endpoint}/{api_index}",
                    api_index,  # sometimes id is just "goblin"
                )
                placeholders = ",".join("?" for _ in id_variants)
                cur.execute(
                    f"""
                    SELECT {self._json_col}
                    FROM {self._table}
                    WHERE {self._id_col} IN ({placeholders})
                    LIMIT 1
                    """,
                    list(id_variants),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return self._loads_json(row[0])

            raise KeyError(
                f"Entity not found in DB for endpoint={endpoint!r}, api_index={api_index!r}. "
                f"(Detected table={self._table!r}, json_col={self._json_col!r}, "
                f"endpoint_col={self._endpoint_col!r}, api_index_col={self._api_index_col!r}, id_col={self._id_col!r})"
            )

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

    def load_monster_combatant(self, api_index: str) -> Combatant:
        raw = self.get_entity_json("monsters", api_index)

        name = str(raw["name"])
        ac = self._parse_ac(raw.get("armor_class"), name=name)

        max_hp = int(raw["hit_points"])
        dex = int(raw["dexterity"])

        attacks: List[AttackProfile] = []
        for a in raw.get("actions", []):
            if not isinstance(a, dict):
                continue
            if "attack_bonus" not in a:
                continue

            dmg_list = a.get("damage") or []
            if not isinstance(dmg_list, list) or not dmg_list:
                continue

            dmg0 = dmg_list[0]
            if not isinstance(dmg0, dict):
                continue

            damage_dice = dmg0.get("damage_dice")
            if not isinstance(damage_dice, str) or not damage_dice.strip():
                continue

            damage_type = (dmg0.get("damage_type") or {}).get("name", "Unknown")
            damage_type_str = str(damage_type)

            attacks.append(
                AttackProfile(
                    name=str(a.get("name", "Attack")),
                    attack_bonus=int(a["attack_bonus"]),
                    damage_dice=damage_dice.strip(),
                    damage_type=damage_type_str,
                )
            )

        if not attacks:
            raise ValueError(f"Monster {name!r} has no usable attacks in DB payload.")

        idx = raw.get("index", api_index)
        return Combatant(
            id=f"monster:{idx}",
            name=name,
            ac=ac,
            max_hp=max_hp,
            hp=max_hp,
            dex=dex,
            attacks=attacks,
        )
