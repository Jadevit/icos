from __future__ import annotations

from icos.kernel.core.state import EncounterState

from icos.game.runtime.actor import Combatant


def team_hp_sum(state: EncounterState[Combatant], team: str) -> int:
    return sum(c.hp for c in state.actors if c.alive and c.team == team)


def enemy_hp_sum(state: EncounterState[Combatant], team: str) -> int:
    return sum(c.hp for c in state.actors if c.alive and c.team != team)


def alive_teams(state: EncounterState[Combatant]) -> set[str]:
    return {c.team for c in state.actors if c.alive}


def evaluate_delta(
    before: EncounterState[Combatant],
    after: EncounterState[Combatant],
    team: str,
) -> float:
    """Positive score means better outcome for `team`."""

    before_enemy = enemy_hp_sum(before, team)
    after_enemy = enemy_hp_sum(after, team)
    before_ally = team_hp_sum(before, team)
    after_ally = team_hp_sum(after, team)

    enemy_damage = before_enemy - after_enemy
    ally_damage = before_ally - after_ally

    score = enemy_damage * 1.0 - ally_damage * 1.2

    before_teams = alive_teams(before)
    after_teams = alive_teams(after)

    if team in after_teams and len(after_teams) == 1:
        score += 10_000.0
    if team not in after_teams and team in before_teams:
        score -= 10_000.0

    return score
