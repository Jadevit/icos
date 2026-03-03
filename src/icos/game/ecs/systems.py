from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .registry import ECSRegistry


SystemFn = Callable[[ECSRegistry, "EventBus", dict[str, object]], None]


@dataclass(frozen=True)
class SystemSpec:
    name: str
    order: int
    fn: SystemFn


class SystemRegistry:
    """Deterministic system scheduler (order, then name)."""

    def __init__(self) -> None:
        self._systems: list[SystemSpec] = []

    def register(self, name: str, fn: SystemFn, *, order: int) -> None:
        self._systems.append(SystemSpec(name=name, order=order, fn=fn))
        self._systems.sort(key=lambda s: (s.order, s.name))

    def run(self, world: ECSRegistry, bus: "EventBus", context: dict[str, object] | None = None) -> None:
        ctx = context if context is not None else {}
        for system in self._systems:
            system.fn(world, bus, ctx)


from icos.game.events.bus import EventBus
