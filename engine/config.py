# engine/config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnginePaths:
    """
    Centralized filesystem layout. These are defaults; callers can override.
    """
    root: Path = Path(".")
    data_dir: Path = Path("data")

    # source content
    content_dir: Path = Path("data/content")

    # compiled artifacts
    bundles_dir: Path = Path("data/bundles")
    codex_dir: Path = Path("data/codex")
    codex_db: Path = Path("data/codex/codex.db")
    codex_manifest: Path = Path("data/codex/manifest.json")
    codex_checksum: Path = Path("data/codex/checksum.txt")

    def abs(self, p: Path) -> Path:
        # Treat paths as repo-relative by default.
        return (self.root / p).resolve()