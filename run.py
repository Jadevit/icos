from __future__ import annotations

import argparse
from typing import List

from engine import IcosEngine
from engine.models import ActionDeclaration, AttackProfile, Combatant
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
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--rollouts", type=int, default=80)
    parser.add_argument("--epsilon", type=float, default=0.02)
    parser.add_argument("--no-build", action="store_true", help="Skip ensure_codex() (dev only)")
    args = parser.parse_args()

    engine = IcosEngine(seed=args.seed)
    if not args.no_build:
        engine.ensure_codex()

    # Build combatants
    gob1 = engine.spawn_monster(
        "goblin",
        team="enemies",
        instance_id="enemy:goblin_1",
        max_hp_override=20,
        heals_remaining=1,
        heal_dice="1d6+1",
    )

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

    # Controllers
    player = PlayerController(registry=engine.registry, prompt=prompt_cli)
    enemy_ai = PlannerController(
        registry=engine.registry,
        config=PlannerConfig(rollouts=args.rollouts, epsilon=args.epsilon, seed=args.seed),
    )

    def print_event(e):
        if e.message:
            print(e.message, flush=True)

    # Encounter builder
    enc = engine.encounter(on_event=print_event)
    enc.add(hero1, controller=player)
    enc.add(gob1, controller=enemy_ai)

    engine.run_encounter(enc)


if __name__ == "__main__":
    main()