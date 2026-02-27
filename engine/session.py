# engine/session.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Mapping, Optional

from .dice import Dice
from .models import ActionDeclaration, Combatant, Event
from .systems.combat.resolution import RulesEngine
from .state import CombatState
from .systems.ai.interface import CombatController


EventSink = Callable[[Event], None]


@dataclass
class CombatSession:
    dice: Dice = field(default_factory=Dice)
    rules: RulesEngine = field(init=False)

    def __post_init__(self) -> None:
        self.rules = RulesEngine(self.dice)

    def run(
        self,
        combatants: List[Combatant],
        controllers: Mapping[str, CombatController],
        max_rounds: int = 50,
        *,
        on_event: Optional[EventSink] = None,
    ) -> List[Event]:
        """
        controllers: mapping of combatant_id -> controller.
        No assumptions about team size. 1v1 is just 2 combatants on different teams.
        """
        state = CombatState(combatants=combatants)
        log: List[Event] = []

        def emit(ev: Event) -> None:
            log.append(ev)
            if on_event is not None and ev.message:
                on_event(ev)

        def emit_many(events: List[Event]) -> None:
            for e in events:
                emit(e)

        order, init_events = self.rules.roll_initiative(combatants)
        state.initiative_order = order
        emit_many(init_events)

        init_names = " -> ".join(state.get(cid).name for cid in order)
        emit(Event(type="combat_end", message=f"Initiative order: {init_names}"))

        while not state.is_over() and state.round_num <= max_rounds:
            actor = state.get(state.current_turn_id())

            if not actor.alive:
                state.advance_turn()
                continue

            # Rule: "defending" lasts until the start of your next turn.
            actor.flags.discard("defending")

            emit(
                Event(
                    type="turn_start",
                    actor=actor.id,
                    message=f"--- Round {state.round_num}, {actor.name} turn ---",
                    data={"round": state.round_num},
                )
            )

            controller = controllers.get(actor.id)
            action = (
                controller.choose_action(state, actor.id)
                if controller is not None
                else ActionDeclaration(actor_id=actor.id, type="wait")
            )

            emit_many(self.rules.resolve_action(state, action))
            state.advance_turn()

        winner = state.winner_team()
        end_msg = f"Combat ends. Winner team: {winner}" if winner else "Combat ends. No winner."
        emit(Event(type="combat_end", message=end_msg))
        return log