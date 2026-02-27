# engine/encounter.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Mapping, Optional

from .models import Combatant, Event
from .systems.ai.interface import CombatController


EventSink = Callable[[Event], None]


@dataclass
class Encounter:
    """
    Lightweight encounter container/builder.

    This is intentionally minimal: it just bundles combatants + controllers and
    gives you a clean place to configure encounters without bloating run.py.

    The engine remains the authority for running/validating the encounter.
    """
    combatants: List[Combatant] = field(default_factory=list)
    controllers: dict[str, CombatController] = field(default_factory=dict)
    max_rounds: int = 50
    on_event: Optional[EventSink] = None

    def add(self, combatant: Combatant, controller: Optional[CombatController] = None) -> "Encounter":
        self.combatants.append(combatant)
        if controller is not None:
            self.controllers[combatant.id] = controller
        return self

    def set_controller(self, combatant_id: str, controller: CombatController) -> "Encounter":
        self.controllers[combatant_id] = controller
        return self

    def set_max_rounds(self, max_rounds: int) -> "Encounter":
        self.max_rounds = max_rounds
        return self

    def set_event_sink(self, on_event: Optional[EventSink]) -> "Encounter":
        self.on_event = on_event
        return self