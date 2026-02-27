# engine/session.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .dice import Dice
from .models import Combatant, Event
from .rules import RulesEngine
from .state import CombatState


@dataclass
class CombatSession:
    dice: Dice = field(default_factory=Dice)
    rules: RulesEngine = field(init=False)

    def __post_init__(self) -> None:
        self.rules = RulesEngine(self.dice)

    def run(self, combatants: List[Combatant], max_rounds: int = 50) -> List[Event]:
        state = CombatState(combatants=combatants)
        log: List[Event] = []

        order, init_events = self.rules.roll_initiative(combatants)
        state.initiative_order = order
        log.extend(init_events)

        init_order_str = " -> ".join(state.get(cid).name for cid in state.initiative_order)
        log.append(Event(type="combat_end", message=f"Initiative order: {init_order_str}"))

        while not state.is_over() and state.round_num <= max_rounds:
            current_id = state.current_turn_id()
            actor = state.get(current_id)

            if not actor.alive:
                state.advance_turn()
                continue

            living = [c for c in state.combatants if c.alive]
            if len(living) <= 1:
                break
            target = next(c for c in living if c.id != actor.id)

            turn_msg = f"--- Round {state.round_num}, {actor.name} turn ---"
            log.append(
                Event(
                    type="turn_start",
                    actor=actor.id,
                    message=turn_msg,
                    data={"round": state.round_num},
                )
            )

            log.extend(self.rules.resolve_basic_attack(state, actor, target))

            if state.is_over():
                break

            state.advance_turn()

        winner_id = state.determine_winner()
        if winner_id:
            winner = state.get(winner_id)
            log.append(Event(type="combat_end", message=f"Combat ends. Winner: {winner.name}"))
        else:
            log.append(Event(type="combat_end", message="Combat ends. No winner (max rounds or draw)."))

        return log
