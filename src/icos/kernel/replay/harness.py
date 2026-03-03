from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, List, TypeVar

from icos.kernel.contracts import EventRecordV1, event_record_from_event
from icos.kernel.core.actor import Actor
from icos.kernel.core.session import EncounterLoop

from .formats import ReplayFileV1
from .replayer import run_replay

TActor = TypeVar("TActor", bound=Actor)


@dataclass(frozen=True)
class ReplayValidationReport:
    exact_match: bool
    expected_event_count: int
    replayed_event_count: int
    first_mismatch_index: int | None = None
    expected_event: dict[str, object] | None = None
    replayed_event: dict[str, object] | None = None


def validate_replay(
    *,
    loop: EncounterLoop[TActor],
    actors: List[TActor],
    replay: ReplayFileV1,
    max_rounds: int = 50,
) -> ReplayValidationReport:
    replayed_events = run_replay(loop=loop, actors=actors, replay=replay, max_rounds=max_rounds)
    replayed_records = [_event_to_dict(event_record_from_event(e)) for e in replayed_events]
    expected_records = [_coerce_event_dict(e) for e in replay.events]

    n = min(len(replayed_records), len(expected_records))
    first_mismatch: int | None = None
    for idx in range(n):
        if replayed_records[idx] != expected_records[idx]:
            first_mismatch = idx
            break

    if first_mismatch is None and len(replayed_records) == len(expected_records):
        return ReplayValidationReport(
            exact_match=True,
            expected_event_count=len(expected_records),
            replayed_event_count=len(replayed_records),
        )

    if first_mismatch is None:
        first_mismatch = n

    expected_event = expected_records[first_mismatch] if first_mismatch < len(expected_records) else None
    replayed_event = replayed_records[first_mismatch] if first_mismatch < len(replayed_records) else None

    return ReplayValidationReport(
        exact_match=False,
        expected_event_count=len(expected_records),
        replayed_event_count=len(replayed_records),
        first_mismatch_index=first_mismatch,
        expected_event=expected_event,
        replayed_event=replayed_event,
    )


def _event_to_dict(record: EventRecordV1) -> dict[str, object]:
    return {str(k): v for k, v in record.to_dict().items()}


def _coerce_event_dict(raw: dict[str, object]) -> dict[str, object]:
    return {str(k): v for k, v in raw.items()}
