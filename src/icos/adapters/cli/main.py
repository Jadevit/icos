from __future__ import annotations

import argparse

from icos.app.services import GameEngine
from icos.adapters.cli import CommandRegistry, DevConsole, DevContext, install_builtin_commands
from icos.game.runtime import ActorBlueprint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-build", action="store_true", help="Skip ensure_codex() (dev only)")
    parser.add_argument(
        "--verbose-events",
        dest="verbose_events",
        action="store_true",
        help="Print structured encounter events to the terminal.",
    )
    parser.add_argument(
        "--no-verbose-events",
        dest="verbose_events",
        action="store_false",
        help="Hide encounter event logs and show only gameplay UI.",
    )
    parser.set_defaults(verbose_events=False)
    args = parser.parse_args()

    engine = GameEngine[ActorBlueprint](seed=args.seed)
    if not args.no_build:
        engine.ensure_codex()

    ctx = DevContext(engine=engine, verbose_events=bool(args.verbose_events))
    registry = CommandRegistry()
    install_builtin_commands(registry)

    DevConsole(ctx=ctx, registry=registry).run()


if __name__ == "__main__":
    main()
