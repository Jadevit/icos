from __future__ import annotations

from dataclasses import dataclass, field

from icos.content.defs.common import DamageType

from .inventory import Inventory


@dataclass(frozen=True)
class AttackProfile:
    name: str
    attack_bonus: int
    damage_dice: str
    damage_type: DamageType
    attack_kind: str = "melee"


@dataclass
class ActorBlueprint:
    """Data-only actor blueprint consumed by ECS runtime conversion."""

    id: str
    name: str
    team: str = "neutral"

    ac: int = 10
    max_hp: int = 1
    hp: int = 1
    dex: int = 10
    attacks: list[AttackProfile] = field(default_factory=list)
    abilities: list[str] = field(default_factory=list)

    heals_remaining: int = 0
    heal_dice: str = "1d8+2"
    conditions: dict[str, int] = field(default_factory=dict)
    inventory: Inventory = field(default_factory=Inventory)

    flags: set[str] = field(default_factory=set)
    alive: bool = True

    position_x: int = 0
    position_y: int = 0
    move_speed: int = 30

    def __post_init__(self) -> None:
        self.ac = max(1, int(self.ac))
        self.max_hp = max(1, int(self.max_hp))
        self.hp = max(0, min(int(self.hp), self.max_hp))
        self.alive = self.hp > 0

        if self.move_speed < 0:
            self.move_speed = 0

        normalized: dict[str, int] = {}
        for key, turns in self.conditions.items():
            nkey = str(key).strip().lower()
            if not nkey:
                continue
            try:
                nturns = int(turns)
            except (TypeError, ValueError):
                nturns = 0
            if nturns > 0:
                normalized[nkey] = nturns
        self.conditions = normalized


# Backward-compatible alias; ActorBlueprint is the canonical runtime blueprint.
Combatant = ActorBlueprint
