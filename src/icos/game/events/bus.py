from __future__ import annotations

from dataclasses import dataclass, field

from icos.tact.events.types import Event


@dataclass
class EventBus:
    """In-memory structured event bus for one deterministic encounter tick."""

    _queue: list[Event] = field(default_factory=list)

    def publish(self, event: Event) -> None:
        self._queue.append(event)

    def publish_many(self, events: list[Event]) -> None:
        self._queue.extend(events)

    def drain(self) -> list[Event]:
        out = list(self._queue)
        self._queue.clear()
        return out

    def __len__(self) -> int:
        return len(self._queue)
