from __future__ import annotations

from dataclasses import dataclass

from icos.content.defs.common import ability_mod
from icos.game.ecs import (
    AbilitySetComponent,
    ArmorComponent,
    AttackProfileComponent,
    AttackProfileData,
    ConditionComponent,
    ECSRegistry,
    FlagComponent,
    HealProfileComponent,
    HealthComponent,
    IdentityComponent,
    InventoryComponent,
    MovementComponent,
    StatsComponent,
)


@dataclass(frozen=True)
class ActorSnapshot:
    id: str
    name: str
    team: str
    alive: bool
    hp: int
    max_hp: int
    ac: int
    dexterity: int
    flags: tuple[str, ...]
    conditions: dict[str, int]
    heals_remaining: int
    heal_dice: str
    attacks: tuple[AttackProfileData, ...]
    attack_bonus_bonus: int
    damage_bonus_bonus: int
    heal_bonus_bonus: int
    move_speed: int
    move_remaining: int
    ability_ids: tuple[str, ...]

    @property
    def dex_mod(self) -> int:
        return ability_mod(self.dexterity)


def actor_snapshot(world: ECSRegistry, actor_id: str) -> ActorSnapshot:
    ident = world.get_component(actor_id, IdentityComponent)
    health = world.get_component(actor_id, HealthComponent)
    armor = world.try_component(actor_id, ArmorComponent)
    stats = world.try_component(actor_id, StatsComponent)
    flags = world.try_component(actor_id, FlagComponent)
    conditions = world.try_component(actor_id, ConditionComponent)
    heals = world.try_component(actor_id, HealProfileComponent)
    attacks = world.try_component(actor_id, AttackProfileComponent)
    inv = world.try_component(actor_id, InventoryComponent)
    move = world.try_component(actor_id, MovementComponent)
    abilities = world.try_component(actor_id, AbilitySetComponent)

    base_ac = armor.base_ac if armor is not None else 10
    inv_ac = inv.ac_bonus if inv is not None else 0

    return ActorSnapshot(
        id=actor_id,
        name=ident.name,
        team=ident.team,
        alive=bool(health.alive),
        hp=int(health.hp),
        max_hp=int(health.max_hp),
        ac=max(1, int(base_ac + inv_ac)),
        dexterity=stats.dexterity if stats is not None else 10,
        flags=tuple(sorted(flags.flags)) if flags is not None else tuple(),
        conditions=dict(conditions.turns) if conditions is not None else {},
        heals_remaining=heals.heals_remaining if heals is not None else 0,
        heal_dice=heals.heal_dice if heals is not None else "1d8+2",
        attacks=attacks.attacks if attacks is not None else tuple(),
        attack_bonus_bonus=inv.attack_bonus if inv is not None else 0,
        damage_bonus_bonus=inv.damage_bonus if inv is not None else 0,
        heal_bonus_bonus=inv.heal_bonus if inv is not None else 0,
        move_speed=move.speed if move is not None else 0,
        move_remaining=move.remaining if move is not None else 0,
        ability_ids=abilities.ability_ids if abilities is not None else tuple(),
    )


def living_enemies(world: ECSRegistry, actor_id: str) -> list[ActorSnapshot]:
    source = actor_snapshot(world, actor_id)
    out: list[ActorSnapshot] = []
    for entity_id, ident, health in world.query(IdentityComponent, HealthComponent):
        if entity_id == actor_id:
            continue
        if not health.alive or ident.team == source.team:
            continue
        out.append(actor_snapshot(world, entity_id))
    out.sort(key=lambda a: (a.hp, a.id))
    return out


def living_allies(world: ECSRegistry, actor_id: str) -> list[ActorSnapshot]:
    source = actor_snapshot(world, actor_id)
    out: list[ActorSnapshot] = []
    for entity_id, ident, health in world.query(IdentityComponent, HealthComponent):
        if not health.alive or ident.team != source.team:
            continue
        out.append(actor_snapshot(world, entity_id))
    out.sort(key=lambda a: a.id)
    return out


def alive_teams(world: ECSRegistry) -> set[str]:
    out: set[str] = set()
    for _, ident, health in world.query(IdentityComponent, HealthComponent):
        if health.alive:
            out.add(ident.team)
    return out


# Backward-compatible alias for older naming.
CombatActorSnapshot = ActorSnapshot
