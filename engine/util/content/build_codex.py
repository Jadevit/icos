#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

Json = Dict[str, Any]


def read_codex_manifest(path: Path) -> List[str]:
    """
    Returns list of pack roots (paths) in load order (low -> high priority).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    enabled = data.get("enabled", [])
    if not isinstance(enabled, list):
        raise ValueError("codex manifest 'enabled' must be a list")
    roots: List[str] = []
    for item in enabled:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            roots.append(item["path"])
    if not roots:
        raise ValueError("codex manifest has no enabled pack paths")
    return roots


def bundle_name_for_pack(pack_root: Path) -> str:
    manifest_path = pack_root / "manifest.json"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        pack_type = str(m.get("type", "pack")).strip().lower().replace(" ", "_")
        pack_name = str(m.get("name", pack_root.name)).strip().lower().replace(" ", "_")

        bundle_override = m.get("bundle")
        if isinstance(bundle_override, str) and bundle_override.strip():
            name = bundle_override.strip()
            if not name.endswith(".db"):
                name += ".db"
            return name
    else:
        pack_type = "pack"
        pack_name = pack_root.name

    if pack_type == "base":
        return "base.db"
    if pack_type == "dlc":
        return f"dlc_{pack_name}.db"
    if pack_type == "mod":
        return f"mod_{pack_name}.db"

    return f"{pack_type}_{pack_name}.db"


def read_bundle_hash(bundle_db: Path) -> str:
    conn = sqlite3.connect(bundle_db.as_posix())
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key='content_hash' LIMIT 1")
        row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else ""
    finally:
        conn.close()


def compute_codex_checksum(pack_roots: List[Path], bundle_dir: Path) -> str:
    h = hashlib.sha256()
    for pack_root in pack_roots:
        bname = bundle_name_for_pack(pack_root)
        bpath = bundle_dir / bname
        h.update(pack_root.as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(bname.encode("utf-8"))
        h.update(b"\0")
        h.update(read_bundle_hash(bpath).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


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
            source_pack TEXT,
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


def merge_codex(pack_roots: List[Path], bundle_dir: Path, out_db: Path) -> str:
    """
    Last writer wins by load order: later packs override earlier ones by id.
    """
    out_db.parent.mkdir(parents=True, exist_ok=True)
    if out_db.exists():
        out_db.unlink()

    checksum = compute_codex_checksum(pack_roots, bundle_dir)

    conn_out = sqlite3.connect(out_db.as_posix())
    try:
        init_db(conn_out)
        cur_out = conn_out.cursor()

        # Merge bundles in order. If id collides, overwrite.
        for pack_root in pack_roots:
            bundle_path = bundle_dir / bundle_name_for_pack(pack_root)
            if not bundle_path.exists():
                raise FileNotFoundError(f"Missing bundle for pack {pack_root}: {bundle_path}")

            conn_in = sqlite3.connect(bundle_path.as_posix())
            try:
                cur_in = conn_in.cursor()
                cur_in.execute("SELECT id, endpoint, api_index, name, json, source_path FROM entities")
                rows = cur_in.fetchall()
            finally:
                conn_in.close()

            source_pack = pack_root.as_posix()
            for (eid, endpoint, api_index, name, raw_json, source_path) in rows:
                cur_out.execute(
                    """
                    INSERT INTO entities(id, endpoint, api_index, name, json, source_pack, source_path)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      endpoint=excluded.endpoint,
                      api_index=excluded.api_index,
                      name=excluded.name,
                      json=excluded.json,
                      source_pack=excluded.source_pack,
                      source_path=excluded.source_path
                    """,
                    (eid, endpoint, api_index, name, raw_json, source_pack, source_path),
                )

            conn_out.commit()

        set_meta(conn_out, "codex_checksum", checksum)
        set_meta(conn_out, "bundle_dir", bundle_dir.as_posix())
        set_meta(conn_out, "pack_count", str(len(pack_roots)))
        set_meta(conn_out, "packs", json.dumps([p.as_posix() for p in pack_roots]))

    finally:
        conn_out.close()

    return checksum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/codex/manifest.json", help="Codex manifest path")
    parser.add_argument("--bundle-dir", default="data/bundles", help="Bundle DB directory")
    parser.add_argument("--out", default="data/codex/codex.db", help="Output codex DB path")
    parser.add_argument("--write-checksum", default="data/codex/checksum.txt", help="Write checksum here")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    bundle_dir = Path(args.bundle_dir)
    out_db = Path(args.out)
    checksum_path = Path(args.write_checksum)

    pack_paths = [Path(p) for p in read_codex_manifest(manifest_path)]
    checksum = merge_codex(pack_paths, bundle_dir, out_db)

    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text(checksum + "\n", encoding="utf-8")

    print(f"Built {out_db} (codex_checksum={checksum})")


if __name__ == "__main__":
    main()