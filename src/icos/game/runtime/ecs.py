from __future__ import annotations

from icos.game.ecs import (
    AbilitySetComponent,
    ArmorComponent,
    AttackProfileComponent,
    AttackProfileData,
    ConditionComponent,
    ECSRegistry,
    EncounterComponent,
    FlagComponent,
    HealProfileComponent,
    HealthComponent,
    IdentityComponent,
    InventoryComponent,
    MovementComponent,
    PositionComponent,
    StatsComponent,
)

from .actor import AttackProfile, ActorBlueprint


ENCOUNTER_ENTITY_ID = "encounter:root"


def build_world_from_actor_blueprints(actor_blueprints: list[ActorBlueprint]) -> ECSRegistry:
    world = ECSRegistry()
    world.create_entity(ENCOUNTER_ENTITY_ID)
    world.add_component(ENCOUNTER_ENTITY_ID, EncounterComponent())

    for actor_blueprint in actor_blueprints:
        world.create_entity(actor_blueprint.id)
        world.add_component(actor_blueprint.id, IdentityComponent(name=actor_blueprint.name, team=actor_blueprint.team))
        world.add_component(
            actor_blueprint.id,
            StatsComponent(
                strength=10,
                dexterity=int(actor_blueprint.dex),
                constitution=10,
                intelligence=10,
                wisdom=10,
                charisma=10,
            ),
        )
        world.add_component(
            actor_blueprint.id,
            HealthComponent(max_hp=int(actor_blueprint.max_hp), hp=int(actor_blueprint.hp), alive=bool(actor_blueprint.alive)),
        )
        world.add_component(actor_blueprint.id, ArmorComponent(base_ac=int(actor_blueprint.ac)))
        world.add_component(actor_blueprint.id, FlagComponent(flags=set(actor_blueprint.flags)))
        world.add_component(actor_blueprint.id, ConditionComponent(turns=dict(actor_blueprint.conditions)))

        mods = actor_blueprint.inventory.modifiers
        item_ids = [item.api_index for item in actor_blueprint.inventory.items]
        item_names = [item.name for item in actor_blueprint.inventory.items]
        world.add_component(
            actor_blueprint.id,
            InventoryComponent(
                item_ids=item_ids,
                item_names=item_names,
                ac_bonus=int(mods.ac_bonus),
                attack_bonus=int(mods.attack_bonus),
                damage_bonus=int(mods.damage_bonus),
                heal_bonus=int(mods.heal_bonus),
            ),
        )

        world.add_component(
            actor_blueprint.id,
            AttackProfileComponent(
                attacks=tuple(
                    AttackProfileData(
                        name=attack.name,
                        attack_bonus=int(attack.attack_bonus),
                        damage_dice=str(attack.damage_dice),
                        damage_type=str(attack.damage_type),
                        attack_kind=str(attack.attack_kind),
                    )
                    for attack in actor_blueprint.attacks
                )
            ),
        )
        world.add_component(
            actor_blueprint.id,
            AbilitySetComponent(
                ability_ids=tuple(str(ability_id) for ability_id in actor_blueprint.abilities),
            ),
        )
        world.add_component(
            actor_blueprint.id,
            HealProfileComponent(
                heals_remaining=int(actor_blueprint.heals_remaining),
                heal_dice=str(actor_blueprint.heal_dice),
            ),
        )
        world.add_component(
            actor_blueprint.id,
            PositionComponent(
                x=int(actor_blueprint.position_x),
                y=int(actor_blueprint.position_y),
            ),
        )
        world.add_component(
            actor_blueprint.id,
            MovementComponent(
                speed=max(0, int(actor_blueprint.move_speed)),
                remaining=max(0, int(actor_blueprint.move_speed)),
            ),
        )

    return world


def snapshot_actor_blueprint(world: ECSRegistry, actor_id: str) -> ActorBlueprint:
    ident = world.get_component(actor_id, IdentityComponent)
    health = world.get_component(actor_id, HealthComponent)
    stats = world.get_component(actor_id, StatsComponent)
    armor = world.get_component(actor_id, ArmorComponent)
    flags = world.get_component(actor_id, FlagComponent)
    conditions = world.get_component(actor_id, ConditionComponent)
    inventory = world.get_component(actor_id, InventoryComponent)
    attacks = world.get_component(actor_id, AttackProfileComponent)
    heals = world.get_component(actor_id, HealProfileComponent)
    abilities = world.get_component(actor_id, AbilitySetComponent)
    position = world.get_component(actor_id, PositionComponent)
    movement = world.get_component(actor_id, MovementComponent)

    return ActorBlueprint(
        id=actor_id,
        name=ident.name,
        team=ident.team,
        ac=armor.base_ac,
        max_hp=health.max_hp,
        hp=health.hp,
        dex=stats.dexterity,
        attacks=[
            AttackProfile(
                name=a.name,
                attack_bonus=a.attack_bonus,
                damage_dice=a.damage_dice,
                damage_type=a.damage_type,
                attack_kind=a.attack_kind,
            )
            for a in attacks.attacks
        ],
        abilities=list(abilities.ability_ids),
        heals_remaining=heals.heals_remaining,
        heal_dice=heals.heal_dice,
        conditions=dict(conditions.turns),
        flags=set(flags.flags),
        alive=bool(health.alive),
        position_x=position.x,
        position_y=position.y,
        move_speed=movement.speed,
    )


# Backward-compatible aliases (deprecated naming).
build_world_from_combatants = build_world_from_actor_blueprints
snapshot_combatant = snapshot_actor_blueprint
