from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict

JsonDict = Dict[str, Any]


@dataclass
class CodexLoader:
    """
    Loader for a compiled SQLite codex.

    Required schema:
      - entities(id TEXT PRIMARY KEY, endpoint TEXT, api_index TEXT, json TEXT, ...)
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
        return self.get_json_by_id(f"{endpoint}:{api_index}")