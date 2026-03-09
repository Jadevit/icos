from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, TypeVar

from icos.tact.contracts import (
    ActionRecordV1,
    EventRecordV1,
    StateRecordV1,
    action_record_from_request,
    event_record_from_event,
    state_record_from_actors,
    to_json_value,
)
from icos.tact.core.actions import ActionRequest
from icos.tact.core.types import ActorLike
from icos.tact.events.types import ACTION_VALIDATED, Event

from .formats import REPLAY_SCHEMA_V1, ReplayFileV1

TActor = TypeVar("TActor", bound=ActorLike)


def extract_validated_actions(events: Iterable[Event]) -> list[ActionRecordV1]:
    out: list[ActionRecordV1] = []
    for event in events:
        if event.type != ACTION_VALIDATED:
            continue

        payload = dict(event.data)
        action_obj = payload.get("action")
        if not isinstance(action_obj, dict):
            continue

        actor_id = action_obj.get("actor_id")
        action_id = action_obj.get("action_id")
        targets = action_obj.get("targets")
        data = action_obj.get("data")
        action_seq = payload.get("action_seq", 0)
        round_num = payload.get("round", 0)
        turn_index = payload.get("turn_index", 0)

        if not isinstance(actor_id, str) or not isinstance(action_id, str):
            continue

        if not isinstance(targets, list):
            targets = []
        if not isinstance(data, dict):
            data = {}

        try:
            seq = int(action_seq)
        except (TypeError, ValueError):
            seq = 0

        try:
            round_i = int(round_num)
        except (TypeError, ValueError):
            round_i = 0

        try:
            turn_i = int(turn_index)
        except (TypeError, ValueError):
            turn_i = 0

        req = ActionRequest(
            actor_id=actor_id,
            action_id=action_id,
            targets=tuple(str(t) for t in targets),
            data={str(k): to_json_value(v) for k, v in data.items()},
        )
        out.append(
            action_record_from_request(
                req,
                action_seq=seq,
                round_num=round_i,
                turn_index=turn_i,
            )
        )

    out.sort(key=lambda a: a.action_seq)
    return out


def build_replay(
    *,
    actors: list[TActor],
    events: list[Event],
    metadata: dict[str, Any] | None = None,
) -> ReplayFileV1:
    state_record: StateRecordV1[TActor] = state_record_from_actors(actors)
    action_records = extract_validated_actions(events)
    event_records = [event_record_from_event(e) for e in events]

    safe_meta = {str(k): to_json_value(v) for k, v in (metadata or {}).items()}
    return ReplayFileV1.build(
        metadata=safe_meta,
        initial_state=state_record,
        actions=action_records,
        events=event_records,
    )


def write_replay(path: str | Path, replay: ReplayFileV1) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(replay.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def read_replay(path: str | Path) -> ReplayFileV1:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))

    schema = raw.get("schema")
    if schema != REPLAY_SCHEMA_V1:
        raise ValueError(f"Unsupported replay schema: {schema!r}")

    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    initial_state = raw.get("initial_state") if isinstance(raw.get("initial_state"), dict) else {}
    actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
    events = raw.get("events") if isinstance(raw.get("events"), list) else []

    return ReplayFileV1(
        metadata={str(k): to_json_value(v) for k, v in metadata.items()},
        initial_state={str(k): to_json_value(v) for k, v in initial_state.items()},
        actions=[a for a in actions if isinstance(a, dict)],
        events=[e for e in events if isinstance(e, dict)],
    )
