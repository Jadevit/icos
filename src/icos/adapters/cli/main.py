from __future__ import annotations

import argparse

from icos.app.services import GameEngine
from icos.adapters.cli import CommandRegistry, DevConsole, DevContext, install_builtin_commands
from icos.game.runtime import Combatant


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-build", action="store_true", help="Skip ensure_codex() (dev only)")
    args = parser.parse_args()

    engine = GameEngine[Combatant](seed=args.seed)
    if not args.no_build:
        engine.ensure_codex()

    ctx = DevContext(engine=engine)
    registry = CommandRegistry()
    install_builtin_commands(registry)

    DevConsole(ctx=ctx, registry=registry).run()


if __name__ == "__main__":
    main()
