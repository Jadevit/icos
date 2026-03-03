from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.session import EncounterController
from icos.kernel.core.state import EncounterState

from icos.game.events import EventBus
from icos.game.runtime.actor import ActorBlueprint
from icos.game.systems import actor_snapshot, ai_action_selection_system

from .actions import ActionRegistry


@dataclass
class PlayerController(EncounterController[ActorBlueprint]):
    """CLI controller for a single actor."""

    registry: ActionRegistry
    prompt: Callable[[EncounterState[ActorBlueprint], object, list[ActionRequest]], ActionRequest]

    def choose_action(self, state: EncounterState[ActorBlueprint], actor_id: str) -> ActionRequest:
        actor = actor_snapshot(_world_from_state(state), actor_id)
        legal = self.registry.list_actions(state, actor_id)
        if not legal:
            return ActionRequest(actor_id=actor.id, action_id="wait")
        return self.prompt(state, actor, legal)


@dataclass(frozen=True)
class PlannerConfig:
    rollouts: int = 0
    epsilon: float = 0.05
    seed: Optional[int] = None
    heal_threshold: float = 0.55
    defend_threshold: float = 0.40


@dataclass
class PlannerController(EncounterController[ActorBlueprint]):
    """Deterministic heuristic combat policy over ECS snapshots."""

    registry: ActionRegistry
    config: PlannerConfig = field(default_factory=PlannerConfig)

    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.config.seed)

    def choose_action(self, state: EncounterState[ActorBlueprint], actor_id: str) -> ActionRequest:
        actor = actor_snapshot(_world_from_state(state), actor_id)
        legal = self.registry.list_actions(state, actor_id)
        if not legal:
            return ActionRequest(actor_id=actor.id, action_id="wait")

        if self.config.epsilon > 0 and self._rng.random() < self.config.epsilon:
            return self._rng.choice(legal)

        world = _world_from_state(state)
        ctx: dict[str, object] = {"actor_id": actor_id, "heal_threshold": self.config.heal_threshold}
        ai_action_selection_system(world, EventBus(), ctx)
        selected = ctx.get("selected_action")
        if isinstance(selected, ActionRequest):
            for action in legal:
                if _same_action(action, selected):
                    return action

        hp_ratio = actor.hp / max(1, actor.max_hp)
        attacks = [a for a in legal if a.action_id == "attack"]
        heal_action = next((a for a in legal if a.action_id == "heal"), None)
        defend_action = next((a for a in legal if a.action_id == "defend"), None)

        if heal_action is not None and hp_ratio <= min(self.config.heal_threshold, 0.35):
            return heal_action

        if attacks:
            attacks.sort(key=lambda a: self._attack_priority(state, a), reverse=True)
            if hp_ratio >= self.config.defend_threshold:
                return attacks[0]

        if defend_action is not None and hp_ratio < self.config.defend_threshold:
            return defend_action

        return attacks[0] if attacks else legal[0]

    def _attack_priority(self, state: EncounterState[ActorBlueprint], action: ActionRequest) -> tuple[float, float]:
        world = _world_from_state(state)
        target = actor_snapshot(world, str(action.targets[0]))
        focus_value = 1.0 - (target.hp / max(1, target.max_hp))
        kill_value = 1.0 if target.hp <= 6 else 0.0
        return kill_value, focus_value


from icos.game.ecs import ECSRegistry


def _same_action(lhs: ActionRequest, rhs: ActionRequest) -> bool:
    return (
        lhs.actor_id == rhs.actor_id
        and lhs.action_id == rhs.action_id
        and tuple(lhs.targets) == tuple(rhs.targets)
        and dict(lhs.data) == dict(rhs.data)
    )


def _world_from_state(state: EncounterState[ActorBlueprint]) -> ECSRegistry:
    world = state.data.get("ecs_world")
    if not isinstance(world, ECSRegistry):
        raise RuntimeError("ECS world unavailable. Encounter must be initialized first.")
    return world
