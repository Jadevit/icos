# engine/session.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .dice import Dice
from .models import ActionDeclaration, Combatant, Event
from .rules import RulesEngine
from .state import CombatState
from .systems.combat.targeting import first_alive_enemy


EventSink = Callable[[Event], None]


def _prompt_player_action(actor: Combatant, target: Optional[Combatant]) -> ActionDeclaration:
    while True:
        print(
            f"\n{actor.name} HP {actor.hp}/{actor.max_hp} | Target: {target.name if target else 'None'}",
            flush=True,
        )
        choice = input("Choose action: [a]ttack, [d]efend, [h]eal, [w]ait > ").strip().lower()

        if choice in ("a", "attack"):
            if target is None:
                print("No target available.", flush=True)
                continue
            return ActionDeclaration(actor_id=actor.id, type="attack", target_ids=[target.id], attack_index=0)

        if choice in ("d", "defend"):
            return ActionDeclaration(actor_id=actor.id, type="defend")

        if choice in ("h", "heal"):
            return ActionDeclaration(actor_id=actor.id, type="heal", target_ids=[actor.id])

        if choice in ("w", "wait"):
            return ActionDeclaration(actor_id=actor.id, type="wait")

        print("Invalid choice. Try again.", flush=True)


def _goblin_policy(actor: Combatant, target: Optional[Combatant]) -> ActionDeclaration:
    if actor.hp <= max(3, actor.max_hp // 4):
        r = actor.dex_mod
        if (actor.hp + r) % 2 == 0:
            return ActionDeclaration(actor_id=actor.id, type="defend")

    if target is None:
        return ActionDeclaration(actor_id=actor.id, type="wait")

    return ActionDeclaration(actor_id=actor.id, type="attack", target_ids=[target.id], attack_index=0)


@dataclass
class CombatSession:
    dice: Dice = field(default_factory=Dice)
    rules: RulesEngine = field(init=False)

    def __post_init__(self) -> None:
        self.rules = RulesEngine(self.dice)

    def _emit(self, events: List[Event], sink: Optional[EventSink]) -> None:
        if sink is None:
            return
        for e in events:
            sink(e)

    def run(
        self,
        combatants: List[Combatant],
        max_rounds: int = 50,
        *,
        on_event: Optional[EventSink] = None,
    ) -> List[Event]:
        state = CombatState(combatants=combatants)
        log: List[Event] = []

        order, init_events = self.rules.roll_initiative(combatants)
        state.initiative_order = order
        log.extend(init_events)
        self._emit(init_events, on_event)

        init_order_str = " -> ".join(state.get(cid).name for cid in state.initiative_order)
        e = Event(type="combat_end", message=f"Initiative order: {init_order_str}")
        log.append(e)
        self._emit([e], on_event)

        while not state.is_over() and state.round_num <= max_rounds:
            actor = state.get(state.current_turn_id())

            if not actor.alive:
                state.advance_turn()
                continue

            # Defend lasts until the start of your next turn.
            actor.flags.discard("defending")

            turn_event = Event(
                type="turn_start",
                actor=actor.id,
                message=f"--- Round {state.round_num}, {actor.name} turn ---",
                data={"round": state.round_num},
            )
            log.append(turn_event)
            self._emit([turn_event], on_event)

            target = first_alive_enemy(state, actor)

            if actor.team == "party":
                action = _prompt_player_action(actor, target)
            else:
                action = _goblin_policy(actor, target)

            resolved = self.rules.resolve_action(state, action)
            log.extend(resolved)
            self._emit(resolved, on_event)

            state.advance_turn()

        winner = state.winner_team()
        end_msg = (
            f"Combat ends. Winner team: {winner}"
            if winner is not None
            else "Combat ends. No winner (max rounds or draw)."
        )
        end_event = Event(type="combat_end", message=end_msg)
        log.append(end_event)
        self._emit([end_event], on_event)

        return log
