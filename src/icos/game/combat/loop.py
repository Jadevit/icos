from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from icos.tact.core.actions import ActionRequest
from icos.tact.core.session import EncounterLoop
from icos.tact.core.state import EncounterState
from icos.tact.events.types import Event

from icos.game.rules.dice import Dice
from icos.game.runtime.actor import ActorBlueprint
from icos.game.effects import AbilityDefinition

from .runtime import CombatEcsRuntime


@dataclass
class CombatLoop(EncounterLoop[ActorBlueprint]):
    """ECS-based combat loop implementation."""

    dice: Dice
    runtime: CombatEcsRuntime = field(default_factory=CombatEcsRuntime)

    def init_encounter(self, state: EncounterState[ActorBlueprint]) -> List[Event]:
        return self.runtime.bootstrap(state, dice=self.dice)

    def before_turn(self, state: EncounterState[ActorBlueprint], actor_id: str) -> List[Event]:
        return self.runtime.before_turn(state, actor_id, dice=self.dice)

    def resolve_action(self, state: EncounterState[ActorBlueprint], action: ActionRequest) -> List[Event]:
        return self.runtime.resolve_action(state, action, dice=self.dice)

    def is_over(self, state: EncounterState[ActorBlueprint]) -> bool:
        return self.runtime.is_over(state)

    def outcome(self, state: EncounterState[ActorBlueprint]) -> Optional[str]:
        return self.runtime.outcome(state)

    def finalize(self, state: EncounterState[ActorBlueprint]) -> List[Event]:
        return []

    # --- Optional hooks consumed by EncounterSession for ECS state updates ---

    def apply_event(self, state: EncounterState[ActorBlueprint], event: Event) -> List[Event]:
        return self.runtime.apply_event(state, event)

    def actor_name(self, state: EncounterState[ActorBlueprint], actor_id: str) -> str:
        return self.runtime.actor_name(state, actor_id)

    def actor_is_alive(self, state: EncounterState[ActorBlueprint], actor_id: str) -> bool:
        return self.runtime.actor_is_alive(state, actor_id)

    def actor_ids(self, state: EncounterState[ActorBlueprint]) -> list[str]:
        return self.runtime.actor_ids(state)

    def state_summary(self, state: EncounterState[ActorBlueprint]) -> dict[str, object]:
        return self.runtime.state_summary(state)

    def advance_turn(self, state: EncounterState[ActorBlueprint]) -> List[Event]:
        return self.runtime.advance_turn(state, dice=self.dice)

    def set_ability_catalog(self, catalog: dict[str, AbilityDefinition]) -> None:
        self.runtime.ability_catalog = dict(catalog)

    def action_intent(self, state: EncounterState[ActorBlueprint], action: ActionRequest) -> dict[str, object]:
        return self.runtime.action_intent(state, action)
