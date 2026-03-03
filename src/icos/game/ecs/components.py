from __future__ import annotations

from dataclasses import dataclass, field


EntityId = str


@dataclass(frozen=True)
class AttackProfileData:
    name: str
    attack_bonus: int
    damage_dice: str
    damage_type: str
    attack_kind: str = "melee"


@dataclass
class IdentityComponent:
    name: str
    team: str


@dataclass
class PositionComponent:
    x: int = 0
    y: int = 0


@dataclass
class MovementComponent:
    speed: int = 30
    remaining: int = 30


@dataclass
class StatsComponent:
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10


@dataclass
class HealthComponent:
    max_hp: int = 1
    hp: int = 1
    alive: bool = True


@dataclass
class ArmorComponent:
    base_ac: int = 10


@dataclass
class FlagComponent:
    flags: set[str] = field(default_factory=set)


@dataclass
class ConditionComponent:
    turns: dict[str, int] = field(default_factory=dict)


@dataclass
class InventoryComponent:
    item_ids: list[str] = field(default_factory=list)
    item_names: list[str] = field(default_factory=list)
    ac_bonus: int = 0
    attack_bonus: int = 0
    damage_bonus: int = 0
    heal_bonus: int = 0


@dataclass
class AttackProfileComponent:
    attacks: tuple[AttackProfileData, ...] = field(default_factory=tuple)


@dataclass
class HealProfileComponent:
    heals_remaining: int = 0
    heal_dice: str = "1d8+2"


@dataclass
class InitiativeComponent:
    total: int = 0
    dex_mod: int = 0


@dataclass
class AbilitySetComponent:
    ability_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class AIProfileComponent:
    policy: str = "planner"


@dataclass
class EncounterComponent:
    round_num: int = 1
    turn_index: int = 0
    turn_order: list[str] = field(default_factory=list)
