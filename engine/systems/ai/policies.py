# engine/systems/ai/policies.py
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from ...dice import Dice
from ...models import ActionDeclaration, Combatant
from ...rules import RulesEngine
from ...state import CombatState
from ..actions.registry import ActionRegistry
from .interface import CombatController


def _team_hp_sum(state: CombatState, team: str) -> int:
    return sum(c.hp for c in state.combatants if c.alive and c.team == team)


def _enemy_hp_sum(state: CombatState, team: str) -> int:
    return sum(c.hp for c in state.combatants if c.alive and c.team != team)


def _alive_teams(state: CombatState) -> set[str]:
    return {c.team for c in state.combatants if c.alive}


def _evaluate_delta(before: CombatState, after: CombatState, team: str) -> float:
    """
    Team-based evaluation (works for 1v1 or teams).

    Positive is good for `team`.
    """
    before_enemy = _enemy_hp_sum(before, team)
    after_enemy = _enemy_hp_sum(after, team)
    before_ally = _team_hp_sum(before, team)
    after_ally = _team_hp_sum(after, team)

    enemy_damage = before_enemy - after_enemy
    ally_damage = before_ally - after_ally

    # Weight ally survival slightly higher than dealing damage.
    score = enemy_damage * 1.0 - ally_damage * 1.2

    # Terminal bonuses
    before_teams = _alive_teams(before)
    after_teams = _alive_teams(after)

    if team in after_teams and len(after_teams) == 1:
        score += 10_000.0
    if team not in after_teams and team in before_teams:
        score -= 10_000.0

    return score


@dataclass
class PlayerController(CombatController):
    """
    CLI controller for one actor at a time.

    The prompt function receives:
      - current state (read-only intent)
      - the actor
      - the list of legal actions to choose from
    """
    registry: ActionRegistry
    prompt: Callable[[CombatState, Combatant, list[ActionDeclaration]], ActionDeclaration]

    def choose_action(self, state: CombatState, actor_id: str) -> ActionDeclaration:
        actor = state.get(actor_id)
        legal = self.registry.list_actions(state, actor)
        return self.prompt(state, actor, legal)


@dataclass(frozen=True)
class PlannerConfig:
    """
    Difficulty knobs.
    rollouts=0 turns this into a single-sample forward model (still uses dice once).
    """
    rollouts: int = 50
    epsilon: float = 0.05
    seed: Optional[int] = None


@dataclass
class PlannerController(CombatController):
    """
    1-ply Monte Carlo planner:
      - enumerate legal actions
      - simulate outcomes
      - pick the best average score (with optional exploration)

    This does not assume 1v1. Scoring is team-based.
    """
    registry: ActionRegistry
    config: PlannerConfig = field(default_factory=PlannerConfig)

    def choose_action(self, state: CombatState, actor_id: str) -> ActionDeclaration:
        actor = state.get(actor_id)
        legal = self.registry.list_actions(state, actor)
        if not legal:
            return ActionDeclaration(actor_id=actor.id, type="wait")

        rng = random.Random(self.config.seed)

        # Exploration knob (lower = more "ruthless", higher = more human/erratic)
        if self.config.epsilon > 0 and rng.random() < self.config.epsilon:
            return rng.choice(legal)

        best_action = legal[0]
        best_score = float("-inf")

        for action in legal:
            score = self._score_action(state, actor.team, action, rng)
            if score > best_score:
                best_score = score
                best_action = action

        return best_action

    def _score_action(self, state: CombatState, team: str, action: ActionDeclaration, rng: random.Random) -> float:
        # Note: deepcopy is okay at this scale. If it becomes slow later, we optimize with state diffs.
        if self.config.rollouts <= 0:
            after = self._simulate_once(state, action, rng)
            return _evaluate_delta(state, after, team)

        total = 0.0
        for _ in range(self.config.rollouts):
            after = self._simulate_once(state, action, rng)
            total += _evaluate_delta(state, after, team)

        return total / float(self.config.rollouts)

    @staticmethod
    def _simulate_once(state: CombatState, action: ActionDeclaration, rng: random.Random) -> CombatState:
        after = copy.deepcopy(state)
        # independent rng per simulation for variance
        rules = RulesEngine(Dice(rng=random.Random(rng.randrange(1_000_000_000))))
        rules.resolve_action(after, action)
        return after