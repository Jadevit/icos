from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.session import EncounterLoop
from icos.kernel.core.state import EncounterState
from icos.kernel.events.types import Event

from icos.game.rules.dice import Dice
from icos.game.runtime.actor import Combatant

from .rules import RulesEngine


@dataclass
class CombatLoop(EncounterLoop[Combatant]):
    """Combat implementation of tact's EncounterLoop protocol."""

    dice: Dice

    def __post_init__(self) -> None:
        self.rules = RulesEngine(self.dice)

    def init_encounter(self, state: EncounterState[Combatant]) -> List[Event]:
        order, events = self.rules.roll_initiative(state.actors)
        state.turn_order = order

        names = " -> ".join(state.get(cid).name for cid in order)
        events.append(Event(type="combat_start", message=f"Initiative order: {names}"))
        return events

    def before_turn(self, state: EncounterState[Combatant], actor_id: str) -> List[Event]:
        actor = state.get(actor_id)
        events: List[Event] = []
        actor.flags.discard("defending")
        for cond in actor.tick_conditions():
            events.append(
                Event(
                    type="condition_expired",
                    actor=actor.id,
                    message=f"{actor.name} is no longer {cond}.",
                    data={"condition": cond},
                )
            )
        return events

    def resolve_action(self, state: EncounterState[Combatant], action: ActionRequest) -> List[Event]:
        return self.rules.resolve_action(state, action)

    def is_over(self, state: EncounterState[Combatant]) -> bool:
        return len({a.team for a in state.actors if a.alive}) <= 1

    def outcome(self, state: EncounterState[Combatant]) -> Optional[str]:
        alive_teams = {a.team for a in state.actors if a.alive}
        if len(alive_teams) == 1:
            return next(iter(alive_teams))
        return None

    def finalize(self, state: EncounterState[Combatant]) -> List[Event]:
        winner = self.outcome(state)
        msg = f"Combat ends. Winner team: {winner}" if winner else "Combat ends. No winner."
        return [Event(type="combat_end", message=msg)]
