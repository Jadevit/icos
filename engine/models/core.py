# engine/models/core.py
from __future__ import annotations

from typing import TypeAlias

DamageType: TypeAlias = str


def ability_mod(score: int) -> int:
    return (score - 10) // 2
