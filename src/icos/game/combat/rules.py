from __future__ import annotations

from dataclasses import dataclass, field

from icos.tact.core.actions import ActionRequest
from icos.tact.core.state import EncounterState
from icos.tact.events.types import Event

from icos.game.rules.dice import Dice
from icos.game.runtime.actor import ActorBlueprint

from .runtime import CombatEcsRuntime


@dataclass
class RulesEngine:
    """Compatibility facade backed by ECS systems."""

    dice: Dice
    runtime: CombatEcsRuntime = field(default_factory=CombatEcsRuntime)

    def roll_initiative(self, state: EncounterState[ActorBlueprint]) -> list[Event]:
        return self.runtime.bootstrap(state, dice=self.dice)

    def resolve_action(self, state: EncounterState[ActorBlueprint], action: ActionRequest) -> list[Event]:
        return self.runtime.resolve_action(state, action, dice=self.dice)

    def apply_event(self, state: EncounterState[ActorBlueprint], event: Event) -> list[Event]:
        return self.runtime.apply_event(state, event)
