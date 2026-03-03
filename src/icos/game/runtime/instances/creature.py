from __future__ import annotations

from dataclasses import dataclass, field

from icos.content.defs.creature import MonsterDefinition
from icos.game.runtime.actor import AttackProfile, ActorBlueprint


@dataclass(frozen=True)
class ActorTemplate:
    """Runtime-ready combat template detached from codex schema details."""

    source_id: str
    api_index: str
    name: str
    team: str

    ac: int
    max_hp: int
    dex: int
    attacks: tuple[AttackProfile, ...] = field(default_factory=tuple)


def monster_to_template(monster: MonsterDefinition, *, team: str = "enemies") -> ActorTemplate:
    ac = monster.armor_class[0].value if monster.armor_class else 10
    attacks = _extract_attacks(monster)
    if not attacks:
        raise ValueError(f"Monster {monster.name!r} has no usable attacks.")

    return ActorTemplate(
        source_id=monster.id,
        api_index=monster.api_index,
        name=monster.name,
        team=team,
        ac=ac,
        max_hp=max(1, int(monster.hit_points)),
        dex=int(monster.abilities.dexterity),
        attacks=tuple(attacks),
    )


def instantiate_actor_blueprint(
    template: ActorTemplate,
    *,
    instance_id: str | None = None,
    team: str | None = None,
    max_hp_override: int | None = None,
    ac_override: int | None = None,
    heals_remaining: int = 0,
    heal_dice: str = "1d8+2",
) -> ActorBlueprint:
    assigned_team = team if team is not None else template.team
    cid = instance_id if instance_id is not None else f"{assigned_team}:{template.api_index}"

    max_hp = template.max_hp if max_hp_override is None else int(max_hp_override)
    max_hp = max(1, max_hp)

    ac = template.ac if ac_override is None else int(ac_override)
    ac = max(1, ac)

    return ActorBlueprint(
        id=cid,
        name=template.name,
        team=assigned_team,
        ac=ac,
        max_hp=max_hp,
        hp=max_hp,
        dex=template.dex,
        attacks=list(template.attacks),
        heals_remaining=heals_remaining,
        heal_dice=heal_dice,
    )


def _extract_attacks(monster: MonsterDefinition) -> list[AttackProfile]:
    attacks: list[AttackProfile] = []
    for action in monster.actions:
        if action.attack_bonus is None or not action.damages:
            continue

        damage = action.damages[0]
        if not damage.damage_dice:
            continue

        damage_type = damage.damage_type.name if damage.damage_type is not None else "Unknown"
        attacks.append(
            AttackProfile(
                name=action.name or "Attack",
                attack_bonus=int(action.attack_bonus),
                damage_dice=damage.damage_dice.strip(),
                damage_type=str(damage_type),
                attack_kind=action.attack_kind or "melee",
            )
        )

    return attacks


# Backward-compatible aliases (deprecated naming).
CombatantTemplate = ActorTemplate
instantiate_combatant = instantiate_actor_blueprint
