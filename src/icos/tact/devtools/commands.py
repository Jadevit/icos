from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Generic, List, Optional, Protocol, TypeVar


TCtx = TypeVar("TCtx")
TCtxVerbose = TypeVar("TCtxVerbose", bound="SupportsVerboseEvents")

CommandFn = Callable[[TCtx, List[str]], Optional[str]]


@dataclass
class Command(Generic[TCtx]):
    name: str
    help: str
    fn: CommandFn[TCtx]


@dataclass
class CommandRegistry(Generic[TCtx]):
    commands: Dict[str, Command[TCtx]] = field(default_factory=dict)
    quick_flow: List[str] = field(default_factory=list)

    def register(self, name: str, help: str, fn: CommandFn[TCtx]) -> None:
        self.commands[name] = Command(name=name, help=help, fn=fn)

    def run(self, ctx: TCtx, argv: List[str]) -> Optional[str]:
        if not argv:
            return None
        cmd = self.commands.get(argv[0])
        if cmd is None:
            return f"Unknown command: {argv[0]!r}. Try: help"
        return cmd.fn(ctx, argv[1:])

    def list_help(self) -> str:
        lines = ["Commands:"]
        for name in sorted(self.commands):
            lines.append(f"  {name:<12} {self.commands[name].help}")
        if self.quick_flow:
            lines.append("")
            lines.append("Quick flow:")
            for idx, step in enumerate(self.quick_flow, start=1):
                lines.append(f"  {idx}) {step}")
        return "\n".join(lines)


class SupportsVerboseEvents(Protocol):
    verbose_events: bool


def install_tact_commands(registry: CommandRegistry[TCtxVerbose]) -> None:
    registry.register("help", "Show command help + examples.", lambda _ctx, _args: registry.list_help())
    registry.register("events", "Toggle JSON event output: events on|off|status", _cmd_events)
    registry.register("/events", "Toggle JSON event output: /events on|off|status", _cmd_events)


def _cmd_events(ctx: SupportsVerboseEvents, args: List[str]) -> str:
    if not args:
        return f"Event output: {'on' if ctx.verbose_events else 'off'}"

    token = args[0].strip().lower()
    if token in {"on", "true", "1"}:
        ctx.verbose_events = True
    elif token in {"off", "false", "0"}:
        ctx.verbose_events = False
    elif token in {"status", "show"}:
        return f"Event output: {'on' if ctx.verbose_events else 'off'}"
    else:
        return "Usage: events on|off|status"

    return f"Event output: {'on' if ctx.verbose_events else 'off'}"
