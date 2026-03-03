from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Deque, Generic, List, Mapping, TypeVar

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.actor import Actor
from icos.kernel.core.session import EncounterController, EncounterLoop, EncounterSession
from icos.kernel.core.state import EncounterState
from icos.kernel.events.types import Event

from .formats import ReplayFileV1

TActor = TypeVar("TActor", bound=Actor)


class ReplayMismatchError(RuntimeError):
    pass


@dataclass
class SequentialReplayController(Generic[TActor], EncounterController[TActor]):
    """Feeds a deterministic pre-recorded action stream to the encounter session."""

    actions: Deque[ActionRequest]

    def choose_action(self, state: EncounterState[TActor], actor_id: str) -> ActionRequest:
        if not self.actions:
            return ActionRequest(actor_id=actor_id, action_id="wait")

        nxt = self.actions[0]
        if nxt.actor_id != actor_id:
            raise ReplayMismatchError(
                f"Replay divergence: expected actor {nxt.actor_id!r}, got {actor_id!r}."
            )

        self.actions.popleft()
        return nxt


def run_replay(
    *,
    loop: EncounterLoop[TActor],
    actors: List[TActor],
    replay: ReplayFileV1,
    max_rounds: int = 50,
) -> List[Event]:
    script = _action_script_from_replay(replay)
    controller = SequentialReplayController[TActor](actions=deque(script))

    actor_copies = deepcopy(actors)
    controllers: Mapping[str, EncounterController[TActor]] = {a.id: controller for a in actor_copies}

    session: EncounterSession[TActor] = EncounterSession()
    return session.run(
        loop=loop,
        actors=actor_copies,
        controllers=controllers,
        max_rounds=max_rounds,
    )


def _action_script_from_replay(replay: ReplayFileV1) -> list[ActionRequest]:
    out: list[ActionRequest] = []
    for entry in replay.actions:
        actor_id = entry.get("actor_id")
        action_id = entry.get("action_id")
        targets = entry.get("targets")
        data = entry.get("data")

        if not isinstance(actor_id, str) or not isinstance(action_id, str):
            continue
        if not isinstance(targets, list):
            targets = []
        if not isinstance(data, dict):
            data = {}

        out.append(
            ActionRequest(
                actor_id=actor_id,
                action_id=action_id,
                targets=tuple(str(t) for t in targets),
                data={str(k): v for k, v in data.items()},
            )
        )

    return out
