from __future__ import annotations

from dataclasses import dataclass, field

from icos.kernel.events.types import EVENT_SCHEMA_V1, Event

from .common import JsonValue, to_json_value


@dataclass(frozen=True)
class EventRecordV1:
    schema: str = EVENT_SCHEMA_V1
    event_seq: int = 0
    type: str = ""
    actor_id: str | None = None
    target_id: str | None = None
    message: str = ""
    data: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "event_seq": self.event_seq,
            "type": self.type,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "message": self.message,
            "data": self.data,
        }


def event_record_from_event(event: Event) -> EventRecordV1:
    payload = to_json_value(dict(event.data))
    data = payload if isinstance(payload, dict) else {"value": payload}

    event_seq = data.get("event_seq", 0)
    try:
        seq = int(event_seq) if isinstance(event_seq, (int, float, str)) else 0
    except ValueError:
        seq = 0

    return EventRecordV1(
        event_seq=seq,
        type=event.type,
        actor_id=event.actor,
        target_id=event.target,
        message=event.message,
        data=data,
    )
