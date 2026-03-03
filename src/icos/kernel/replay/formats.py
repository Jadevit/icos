from __future__ import annotations

from dataclasses import dataclass, field

from icos.kernel.contracts import ActionRecordV1, EventRecordV1, StateRecordV1
from icos.kernel.contracts.common import JsonValue

REPLAY_SCHEMA_V1 = "icos.replay.v1"


@dataclass(frozen=True)
class ReplayFileV1:
    schema: str = REPLAY_SCHEMA_V1
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    initial_state: dict[str, JsonValue] = field(default_factory=dict)
    actions: list[dict[str, JsonValue]] = field(default_factory=list)
    events: list[dict[str, JsonValue]] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        *,
        metadata: dict[str, JsonValue],
        initial_state: StateRecordV1,
        actions: list[ActionRecordV1],
        events: list[EventRecordV1],
    ) -> "ReplayFileV1":
        return cls(
            metadata=metadata,
            initial_state=initial_state.to_dict(),
            actions=[a.to_dict() for a in actions],
            events=[e.to_dict() for e in events],
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "metadata": self.metadata,
            "initial_state": self.initial_state,
            "actions": self.actions,
            "events": self.events,
        }
