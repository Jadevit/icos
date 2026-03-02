from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContentPaths:
    """
    Filesystem layout for game content and compiled artifacts.

    All paths are interpreted as project-root relative unless otherwise specified.
    """
    root: Path = Path(".")
    data_dir: Path = Path("data")

    # Source content
    content_dir: Path = Path("data/packs")

    # Compiled artifacts
    bundles_dir: Path = Path("data/bundles")
    codex_dir: Path = Path("data/codex")
    codex_db: Path = Path("data/codex/codex.db")
    codex_manifest: Path = Path("data/codex/manifest.json")
    codex_checksum: Path = Path("data/codex/checksum.txt")

    def abs(self, p: Path) -> Path:
        return (self.root / p).resolve()