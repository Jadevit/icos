from __future__ import annotations

from dataclasses import dataclass, field

from icos.tact.core.actions import ActionRequest

from .common import JsonValue, to_json_dict

ACTION_SCHEMA_V1 = "icos.action.v1"


@dataclass(frozen=True)
class ActionRecordV1:
    schema: str = ACTION_SCHEMA_V1
    action_seq: int = 0
    round: int = 0
    turn_index: int = 0
    actor_id: str = ""
    action_id: str = ""
    targets: tuple[str, ...] = field(default_factory=tuple)
    data: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return to_json_dict(self)


def action_record_from_request(
    action: ActionRequest,
    *,
    action_seq: int,
    round_num: int,
    turn_index: int,
) -> ActionRecordV1:
    safe_data = to_json_dict(dict(action.data))

    return ActionRecordV1(
        action_seq=action_seq,
        round=round_num,
        turn_index=turn_index,
        actor_id=action.actor_id,
        action_id=action.action_id,
        targets=tuple(str(t) for t in action.targets),
        data=safe_data,
    )
