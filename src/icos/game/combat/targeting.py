from __future__ import annotations

from typing import List

from icos.kernel.core.state import EncounterState

from icos.game.runtime.actor import Combatant


def living_enemies(state: EncounterState[Combatant], actor: Combatant) -> List[Combatant]:
    return [c for c in state.actors if c.alive and c.team != actor.team]


def living_allies(state: EncounterState[Combatant], actor: Combatant) -> List[Combatant]:
    return [c for c in state.actors if c.alive and c.team == actor.team]
