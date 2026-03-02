from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator

JsonDict = Dict[str, Any]


@dataclass(frozen=True)
class EntityRow:
    id: str
    endpoint: str
    api_index: str
    name: str
    json: JsonDict


class CodexDb:
    """Read-only typed access to codex entities table."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

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
        cols = {row[1] for row in cur.fetchall()}
        required = {"id", "endpoint", "api_index", "json", "name"}
        missing = required - cols
        if missing:
            raise RuntimeError(f"Invalid codex DB: entities table missing columns: {sorted(missing)}")

    def get_row(self, endpoint: str, api_index: str) -> EntityRow:
        with self._connect() as conn:
            self._assert_schema(conn)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, endpoint, api_index, COALESCE(name, ''), json "
                "FROM entities WHERE endpoint = ? AND api_index = ? LIMIT 1",
                (endpoint, api_index),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"Entity not found: {endpoint}:{api_index}")

            return EntityRow(
                id=str(row[0]),
                endpoint=str(row[1]),
                api_index=str(row[2]),
                name=str(row[3]),
                json=self._loads_json(row[4]),
            )

    def iter_endpoint(self, endpoint: str, *, limit: int | None = None) -> Iterator[EntityRow]:
        with self._connect() as conn:
            self._assert_schema(conn)
            cur = conn.cursor()

            sql = (
                "SELECT id, endpoint, api_index, COALESCE(name, ''), json "
                "FROM entities WHERE endpoint = ? ORDER BY api_index"
            )
            params: tuple[Any, ...]
            if limit is not None:
                sql += " LIMIT ?"
                params = (endpoint, int(limit))
            else:
                params = (endpoint,)

            cur.execute(sql, params)
            rows = cur.fetchall()

        for row in rows:
            yield EntityRow(
                id=str(row[0]),
                endpoint=str(row[1]),
                api_index=str(row[2]),
                name=str(row[3]),
                json=self._loads_json(row[4]),
            )

    def list_endpoints(self) -> Iterable[str]:
        with self._connect() as conn:
            self._assert_schema(conn)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT endpoint FROM entities ORDER BY endpoint")
            for (endpoint,) in cur.fetchall():
                if isinstance(endpoint, str):
                    yield endpoint

    def count_by_endpoint(self) -> Dict[str, int]:
        with self._connect() as conn:
            self._assert_schema(conn)
            cur = conn.cursor()
            cur.execute("SELECT endpoint, COUNT(*) FROM entities GROUP BY endpoint ORDER BY endpoint")
            out: Dict[str, int] = {}
            for endpoint, count in cur.fetchall():
                if isinstance(endpoint, str):
                    out[endpoint] = int(count)
            return out
