# run.py
from __future__ import annotations

import argparse

from engine.dice import Dice
from engine.loader import DbLoader
from engine.models import Combatant, AttackProfile
from engine.session import CombatSession


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/ref.db", help="Path to local ref.db")
    parser.add_argument("--seed", type=int, default=None, help="Seed for deterministic rolls")
    args = parser.parse_args()

    dice = Dice(seed=args.seed) if args.seed is not None else Dice()

    loader = DbLoader(db_path=args.db)
    goblin = loader.load_monster_combatant("goblin")

    hero = Combatant(
        id="pc:hero",
        name="Hero",
        ac=16,
        max_hp=20,
        hp=20,
        dex=12,
        attacks=[
            AttackProfile(
                name="Longsword",
                attack_bonus=5,
                damage_dice="1d8+3",
                damage_type="Slashing",
            )
        ],
    )

    session = CombatSession(dice=dice)
    events = session.run([hero, goblin])

    for e in events:
        if e.message:
            print(e.message)


if __name__ == "__main__":
    main()
