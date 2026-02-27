#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

Json = Dict[str, Any]


@dataclass(frozen=True)
class SourceFile:
    endpoint: str
    api_index: str
    path: Path


def iter_pack_json_files(pack_root: Path) -> List[SourceFile]:
    """
    pack_root layout:
      <pack_root>/
        manifest.json
        monsters/*.json
        spells/*.json
        equipment/*.json
        ...

    We ignore manifest.json and only compile endpoint folders.
    """
    files: List[SourceFile] = []
    for p in pack_root.rglob("*.json"):
        if p.name == "manifest.json":
            continue
        rel = p.relative_to(pack_root)
        if len(rel.parts) < 2:
            continue
        endpoint = rel.parts[0]
        api_index = p.stem
        files.append(SourceFile(endpoint=endpoint, api_index=api_index, path=p))
    files.sort(key=lambda x: (x.endpoint, x.api_index, x.path.as_posix()))
    return files


def compute_hash(files: List[SourceFile]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(f.endpoint.encode("utf-8"))
        h.update(b"\0")
        h.update(f.api_index.encode("utf-8"))
        h.update(b"\0")
        h.update(f.path.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def read_manifest(pack_root: Path) -> Json:
    mpath = pack_root / "manifest.json"
    if not mpath.exists():
        # allow pack without manifest during early dev
        return {"type": "pack", "name": pack_root.name, "version": "0.0.0"}
    return json.loads(mpath.read_text(encoding="utf-8"))


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            endpoint TEXT NOT NULL,
            api_index TEXT NOT NULL,
            name TEXT,
            json TEXT NOT NULL,
            source_path TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_endpoint_index ON entities(endpoint, api_index)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def bundle_pack(pack_root: Path, out_db: Path) -> str:
    files = iter_pack_json_files(pack_root)
    content_hash = compute_hash(files)

    manifest = read_manifest(pack_root)
    pack_type = str(manifest.get("type", "pack"))
    pack_name = str(manifest.get("name", pack_root.name))
    pack_version = str(manifest.get("version", "0.0.0"))

    out_db.parent.mkdir(parents=True, exist_ok=True)
    if out_db.exists():
        out_db.unlink()

    conn = sqlite3.connect(out_db.as_posix())
    try:
        init_db(conn)
        cur = conn.cursor()

        for f in files:
            raw = json.loads(f.path.read_text(encoding="utf-8"))
            name = raw.get("name") if isinstance(raw.get("name"), str) else None

            entity_id = f"{f.endpoint}:{f.api_index}"
            cur.execute(
                """
                INSERT INTO entities(id, endpoint, api_index, name, json, source_path)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (entity_id, f.endpoint, f.api_index, name, json.dumps(raw), f.path.as_posix()),
            )

        conn.commit()

        set_meta(conn, "pack_type", pack_type)
        set_meta(conn, "pack_name", pack_name)
        set_meta(conn, "pack_version", pack_version)
        set_meta(conn, "pack_root", pack_root.as_posix())
        set_meta(conn, "content_hash", content_hash)

    finally:
        conn.close()

    return content_hash


def default_bundle_name(pack_root: Path) -> str:
    manifest = read_manifest(pack_root)

    bundle_override = manifest.get("bundle")
    if isinstance(bundle_override, str) and bundle_override.strip():
        name = bundle_override.strip()
        if not name.endswith(".db"):
            name += ".db"
        return name

    pack_type = str(manifest.get("type", "pack")).strip().lower().replace(" ", "_")
    pack_name = str(manifest.get("name", pack_root.name)).strip().lower().replace(" ", "_")

    if pack_type == "base":
        return "base.db"
    if pack_type == "dlc":
        return f"dlc_{pack_name}.db"
    if pack_type == "mod":
        return f"mod_{pack_name}.db"

    return f"{pack_type}_{pack_name}.db"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", action="append", required=True, help="Pack folder (repeatable)")
    parser.add_argument("--out-dir", default="data/bundles", help="Output directory for bundle DBs")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for p in args.pack:
        pack_root = Path(p)
        out_db = out_dir / default_bundle_name(pack_root)
        h = bundle_pack(pack_root, out_db)
        print(f"Bundled {pack_root} -> {out_db} (hash={h})")


if __name__ == "__main__":
    main()