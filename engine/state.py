# engine/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .models import Combatant


@dataclass
class CombatState:
    """
    Mutable per-encounter state container.

    Note: this is intentionally "dumb". It stores state + provides small helpers.
    Rules live in RulesEngine; controllers decide actions.
    """
    combatants: List[Combatant]
    round_num: int = 1
    turn_index: int = 0
    initiative_order: List[str] = field(default_factory=list)

    _by_id: Dict[str, Combatant] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {c.id: c for c in self.combatants}
        if len(self._by_id) != len(self.combatants):
            raise ValueError("Duplicate combatant ids detected.")

    def get(self, cid: str) -> Combatant:
        try:
            return self._by_id[cid]
        except KeyError as e:
            raise KeyError(f"Combatant not found: {cid}") from e

    def alive_combatants(self) -> List[Combatant]:
        return [c for c in self.combatants if c.alive]

    def alive_teams(self) -> Set[str]:
        return {c.team for c in self.combatants if c.alive}

    def is_over(self) -> bool:
        # Combat ends when <= 1 team has living combatants.
        return len(self.alive_teams()) <= 1

    def winner_team(self) -> Optional[str]:
        teams = list(self.alive_teams())
        return teams[0] if len(teams) == 1 else None

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
        cid = self.initiative_order[self.turn_index]
        if cid not in self._by_id:
            raise KeyError(f"initiative_order references unknown combatant id: {cid}")
        return cid