# run.py
from __future__ import annotations

import argparse
from typing import List

from engine.dice import Dice
from engine.loader import DbLoader
from engine.models import ActionDeclaration, AttackProfile, Combatant
from engine.session import CombatSession
from engine.systems.actions.registry import ActionRegistry
from engine.systems.ai.policies import PlannerConfig, PlannerController, PlayerController


def prompt_cli(state, actor: Combatant, legal: List[ActionDeclaration]) -> ActionDeclaration:
    heals = f"{actor.heals_remaining} heals left" if actor.heals_remaining > 0 else "no heals"
    print(f"\n{actor.name} HP {actor.hp}/{actor.max_hp} | {heals}", flush=True)

    for i, a in enumerate(legal):
        if a.type == "attack" and a.target_ids:
            tgt = state.get(a.target_ids[0]).name
            print(f"{i}) attack -> {tgt}", flush=True)
        else:
            print(f"{i}) {a.type}", flush=True)

    while True:
        choice = input("Choose action # > ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(legal):
                return legal[idx]
        print("Invalid choice.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/codex/codex.db", help="Path to compiled codex DB")
    parser.add_argument("--seed", type=int, default=None, help="Seed for deterministic rolls")
    parser.add_argument("--rollouts", type=int, default=80, help="AI rollouts per action (0 = no sim)")
    parser.add_argument("--epsilon", type=float, default=0.02, help="AI exploration rate (0..1)")
    args = parser.parse_args()

    dice = Dice(seed=args.seed) if args.seed is not None else Dice()
    loader = DbLoader(db_path=args.db)

    # Enemy from DB
    gob1 = loader.load_monster_combatant("goblin", team="enemies", instance_id="enemy:goblin_1")
    gob1.heals_remaining = 0  # goblin doesn't heal (for now)

    # Hardcoded PC (combat-focused phase; no character creation yet)
    hero1 = Combatant(
        id="party:hero_1",
        name="Hero 1",
        team="party",
        ac=16,
        max_hp=20,
        hp=20,
        dex=12,
        attacks=[AttackProfile(name="Longsword", attack_bonus=5, damage_dice="1d8+3", damage_type="Slashing")],
        heals_remaining=3,
        heal_dice="1d8+2",
    )

    registry = ActionRegistry()

    player = PlayerController(registry=registry, prompt=prompt_cli)
    enemy_ai = PlannerController(
        registry=registry,
        config=PlannerConfig(rollouts=args.rollouts, epsilon=args.epsilon, seed=args.seed),
    )

    controllers = {
        hero1.id: player,
        gob1.id: enemy_ai,
    }

    def print_event(e):
        if e.message:
            print(e.message, flush=True)

    session = CombatSession(dice=dice)
    session.run([hero1, gob1], controllers=controllers, on_event=print_event)


if __name__ == "__main__":
    main()