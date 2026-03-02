from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Optional

from .commands import CommandRegistry
from .context import DevContext


@dataclass
class DevConsole:
    ctx: DevContext
    registry: CommandRegistry

    prompt: str = "icos> "

    def run(self) -> None:
        print("Icos Dev Console. Type 'help' for commands. 'quit' to exit.")
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

            out: Optional[str] = None
            try:
                out = self.registry.run(self.ctx, argv)
            except Exception as exc:  # dev console intentionally keeps running
                self.ctx.last_error = str(exc)
                print(f"ERROR: {exc}")
                continue

            if out:
                print(out)
