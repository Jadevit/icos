# engine/models/core.py
from __future__ import annotations

from typing import TypeAlias

DamageType: TypeAlias = str


def ability_mod(score: int) -> int:
    """
    5e-style ability modifier.
    Kept here (core) because multiple systems will use it (combat, checks, saves, etc.).
    """
    return (score - 10) // 2