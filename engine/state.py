# engine/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from .models import Combatant


@dataclass
class CombatState:
    combatants: List[Combatant]
    round_num: int = 1
    turn_index: int = 0
    initiative_order: List[str] = field(default_factory=list)  # list of combatant ids

    def get(self, cid: str) -> Combatant:
        for c in self.combatants:
            if c.id == cid:
                return c
        raise KeyError(f"Combatant not found: {cid}")

    def alive_combatants(self) -> List[Combatant]:
        return [c for c in self.combatants if c.alive]

    def alive_teams(self) -> Set[str]:
        return {c.team for c in self.combatants if c.alive}

    def is_over(self) -> bool:
        return len(self.alive_teams()) <= 1

    def winner_team(self) -> Optional[str]:
        teams = list(self.alive_teams())
        if len(teams) == 1:
            return teams[0]
        return None

    def advance_turn(self) -> None:
        if not self.initiative_order:
            raise ValueError("initiative_order not set.")

        self.turn_index += 1
        if self.turn_index >= len(self.initiative_order):
            self.turn_index = 0
            self.round_num += 1

    def current_turn_id(self) -> str:
        if not self.initiative_order:
            raise ValueError("initiative_order not set.")
        return self.initiative_order[self.turn_index]
