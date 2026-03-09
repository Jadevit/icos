from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Generic, TypeVar

from .commands import CommandRegistry

TCtx = TypeVar("TCtx")


@dataclass
class DevConsole(Generic[TCtx]):
    ctx: TCtx
    registry: CommandRegistry[TCtx]
    prompt: str = "icos> "
    banner: str = "Icos Dev Console. Type 'help' for commands. 'quit' to exit."

    def run(self) -> None:
        print(self.banner)
        while True:
            try:
                raw = input(self.prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return

            if not raw:
                continue
            if raw in ("quit", "exit"):
                return

            try:
                argv = shlex.split(raw)
            except ValueError as exc:
                print(f"Parse error: {exc}")
                continue

            try:
                out = self.registry.run(self.ctx, argv)
            except Exception as exc:  # console keeps running by design
                if hasattr(self.ctx, "last_error"):
                    setattr(self.ctx, "last_error", str(exc))
                print(f"ERROR: {exc}")
                continue

            if out:
                print(out)
