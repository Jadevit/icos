from __future__ import annotations

from typing import Optional

from icos.content.defs.creature import MonsterDefinition
from icos.game.runtime.actor import ActorBlueprint
from icos.game.runtime.instances import instantiate_actor_blueprint, monster_to_template


def monster_to_actor_blueprint(
    monster: MonsterDefinition,
    *,
    team: str = "enemies",
    instance_id: Optional[str] = None,
    max_hp_override: Optional[int] = None,
    ac_override: Optional[int] = None,
    heals_remaining: int = 0,
    heal_dice: str = "1d8+2",
) -> ActorBlueprint:
    template = monster_to_template(monster, team=team)
    return instantiate_actor_blueprint(
        template,
        instance_id=instance_id,
        team=team,
        max_hp_override=max_hp_override,
        ac_override=ac_override,
        heals_remaining=heals_remaining,
        heal_dice=heal_dice,
    )


# Backward-compatible alias (deprecated naming).
monster_to_combatant = monster_to_actor_blueprint
