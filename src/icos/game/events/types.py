from __future__ import annotations

from icos.kernel.events.types import (
    ACTION_APPLIED,
    ACTION_REQUESTED,
    ACTION_RESOLVED,
    ACTION_VALIDATED,
    ENCOUNTER_ENDED,
    ENCOUNTER_STARTED,
    ROUND_ENDED,
    ROUND_STARTED,
    TURN_ENDED,
    TURN_SKIPPED,
    TURN_STARTED,
)


INITIATIVE_ROLLED = "initiative.rolled"
TURN_ORDER_SET = "turn.order_set"
TURN_ADVANCED = "turn.advanced"
TURN_CONTEXT_RESET = "turn.context_reset"

ABILITY_USED = "ability.used"
ABILITY_EFFECT_APPLIED = "ability.effect_applied"
CHECK_ROLLED = "check.rolled"
ATTACK_STARTED = "attack.started"
DAMAGE_APPLIED = "damage.applied"
HEAL_APPLIED = "heal.applied"
HP_CHANGED = "hp.changed"
ENTITY_DIED = "entity.died"
CONDITION_APPLIED = "condition.applied"
CONDITION_TICKED = "condition.ticked"
CONDITION_EXPIRED = "condition.expired"
MOVEMENT_APPLIED = "movement.applied"
MOVED = MOVEMENT_APPLIED
STATS_MODIFIED = "stats.modified"
AI_ACTION_SELECTED = "ai.action_selected"
