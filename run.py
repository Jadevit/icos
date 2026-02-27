# run.py (only main body shown; keep your argparse/seed stuff if you have it)
from __future__ import annotations

import argparse

from engine.dice import Dice
from engine.loader import DbLoader
from engine.models import AttackProfile, Combatant
from engine.session import CombatSession


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/ref.db", help="Path to local ref.db")
    parser.add_argument("--seed", type=int, default=None, help="Seed for deterministic rolls")
    args = parser.parse_args()

    dice = Dice(seed=args.seed) if args.seed is not None else Dice()

    loader = DbLoader(db_path=args.db)

    gob1 = loader.load_monster_combatant("goblin", team="enemies", instance_id="enemy:goblin_1")

    hero1 = Combatant(
        id="party:hero_1",
        name="Hero 1",
        team="party",
        ac=16,
        max_hp=20,
        hp=20,
        dex=12,
        attacks=[AttackProfile(name="Longsword", attack_bonus=5, damage_dice="1d8+3", damage_type="Slashing")],
    )

    # in run.py, after you build session + combatants:

    def print_event(e):
        if e.message:
            print(e.message, flush=True)

    session = CombatSession(dice=dice)
    session.run([hero1, gob1], on_event=print_event)


if __name__ == "__main__":
    main()
