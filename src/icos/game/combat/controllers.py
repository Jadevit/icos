from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.session import EncounterController
from icos.kernel.core.state import EncounterState

from icos.game.rules.dice import Dice, parse_dice
from icos.game.runtime.actor import Combatant

from .actions import ActionRegistry
from .rules import RulesEngine
from .scoring import evaluate_delta


@dataclass
class PlayerController(EncounterController[Combatant]):
    """CLI controller for a single actor."""

    registry: ActionRegistry
    prompt: Callable[[EncounterState[Combatant], Combatant, list[ActionRequest]], ActionRequest]

    def choose_action(self, state: EncounterState[Combatant], actor_id: str) -> ActionRequest:
        actor = state.get(actor_id)
        legal = self.registry.list_actions(state, actor)
        if not legal:
            return ActionRequest(actor_id=actor.id, action_id="wait")
        return self.prompt(state, actor, legal)


@dataclass(frozen=True)
class PlannerConfig:
    rollouts: int = 50
    epsilon: float = 0.05
    seed: Optional[int] = None
    heal_threshold: float = 0.55
    defend_threshold: float = 0.40


@dataclass
class PlannerController(EncounterController[Combatant]):
    """Heuristic + Monte Carlo combat policy."""

    registry: ActionRegistry
    config: PlannerConfig = field(default_factory=PlannerConfig)

    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.config.seed)

    def choose_action(self, state: EncounterState[Combatant], actor_id: str) -> ActionRequest:
        actor = state.get(actor_id)
        legal = self.registry.list_actions(state, actor)
        if not legal:
            return ActionRequest(actor_id=actor.id, action_id="wait")

        if self.config.epsilon > 0 and self._rng.random() < self.config.epsilon:
            return self._rng.choice(legal)

        hp_ratio = actor.hp / max(1, actor.max_hp)
        attacks = [a for a in legal if a.action_id == "attack"]
        heal_action = next((a for a in legal if a.action_id == "heal"), None)

        if heal_action is not None and hp_ratio <= min(self.config.heal_threshold, 0.30):
            return heal_action

        if attacks and hp_ratio >= self.config.defend_threshold:
            return max(attacks, key=lambda a: self._score_action(state, actor.team, a) + self._heuristic_bonus(state, a))

        best = legal[0]
        best_score = float("-inf")

        for action in legal:
            rollout_score = self._score_action(state, actor.team, action)
            heuristic_score = self._heuristic_bonus(state, action)
            score = rollout_score + heuristic_score
            if score > best_score:
                best_score = score
                best = action

        return best

    def _score_action(
        self,
        state: EncounterState[Combatant],
        team: str,
        action: ActionRequest,
    ) -> float:
        if self.config.rollouts <= 0:
            after = self._simulate_once(state, action)
            return evaluate_delta(state, after, team)

        total = 0.0
        for _ in range(self.config.rollouts):
            after = self._simulate_once(state, action)
            total += evaluate_delta(state, after, team)

        return total / float(self.config.rollouts)

    def _simulate_once(
        self,
        state: EncounterState[Combatant],
        action: ActionRequest,
    ) -> EncounterState[Combatant]:
        after: EncounterState[Combatant] = copy.deepcopy(state)
        rules = RulesEngine(Dice(rng=random.Random(self._rng.randrange(1_000_000_000))))
        rules.resolve_action(after, action)

        actor_team = after.get(action.actor_id).team
        enemy_response = self._pick_enemy_response(after, actor_team=actor_team, focus_target=action.actor_id)
        if enemy_response is not None:
            rules.resolve_action(after, enemy_response)

        return after

    def _pick_enemy_response(
        self,
        state: EncounterState[Combatant],
        *,
        actor_team: str,
        focus_target: str,
    ) -> ActionRequest | None:
        enemies = [a for a in state.actors if a.alive and a.team != actor_team]
        if not enemies:
            return None

        enemy = min(enemies, key=lambda a: a.hp)
        legal = self.registry.list_actions(state, enemy)
        if not legal:
            return None

        hp_ratio = enemy.hp / max(enemy.max_hp, 1)
        heal = next((a for a in legal if a.action_id == "heal"), None)
        if heal is not None and hp_ratio <= 0.35:
            return heal

        focused_attacks = [
            a for a in legal if a.action_id == "attack" and a.targets and a.targets[0] == focus_target
        ]
        if focused_attacks:
            return focused_attacks[0]

        attacks = [a for a in legal if a.action_id == "attack" and a.targets]
        if attacks:
            attacks.sort(key=lambda a: self._attack_sort_key(state, enemy, a), reverse=True)
            return attacks[0]

        defend = next((a for a in legal if a.action_id == "defend"), None)
        if defend is not None:
            return defend

        return next((a for a in legal if a.action_id == "wait"), None)

    def _attack_sort_key(
        self,
        state: EncounterState[Combatant],
        actor: Combatant,
        action: ActionRequest,
    ) -> tuple[float, float]:
        target = state.get(action.targets[0])
        expected_damage = self._estimate_attack_damage(actor, action)
        kill_value = 1.0 if target.hp <= expected_damage else 0.0
        focus_value = 1.0 - (target.hp / max(1, target.max_hp))
        return kill_value, focus_value

    def _heuristic_bonus(self, state: EncounterState[Combatant], action: ActionRequest) -> float:
        actor = state.get(action.actor_id)
        hp_ratio = actor.hp / max(1, actor.max_hp)

        if action.action_id == "heal":
            missing = actor.max_hp - actor.hp
            urgency = (1.0 - hp_ratio) * 7.0
            threshold_bonus = 2.5 if hp_ratio <= self.config.heal_threshold else -1.0
            return urgency + threshold_bonus + min(2.0, missing / 8.0)

        if action.action_id == "defend":
            enemy_count = sum(1 for a in state.actors if a.alive and a.team != actor.team)
            if hp_ratio > self.config.defend_threshold:
                return -1.5 + (enemy_count * 0.05)
            urgency = (1.0 - hp_ratio) * 5.0
            return urgency + 1.0 + (enemy_count * 0.15)

        if action.action_id == "attack" and action.targets:
            target = state.get(action.targets[0])
            expected_damage = self._estimate_attack_damage(actor, action)
            kill_bonus = 4.0 if target.hp <= expected_damage else 0.0
            focus_bonus = (1.0 - (target.hp / max(1, target.max_hp))) * 1.5
            return 1.0 + kill_bonus + focus_bonus

        if action.action_id == "wait":
            return -2.0

        return 0.0

    @staticmethod
    def _estimate_attack_damage(actor: Combatant, action: ActionRequest) -> float:
        if action.action_id != "attack":
            return 0.0

        attack_index = int(action.data.get("attack_index", 0))
        attack = actor.choose_attack(attack_index)

        try:
            expr = parse_dice(attack.damage_dice)
            average = expr.num_dice * (expr.sides + 1) / 2.0 + expr.modifier
        except Exception:
            average = 1.0

        return max(0.0, average + actor.equipment_damage_bonus)
