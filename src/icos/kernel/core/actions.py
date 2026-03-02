from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ActionRequest:
    """
    Generic declared intent. Tact does not interpret "attack" or "heal".
    The game defines action ids and payload schema.

    Examples (Icos-level):
      action_id="attack", targets=["enemy:goblin_1"], data={"attack_index": 0}
      action_id="use_item", targets=["party:hero_1"], data={"item_id": "potion_heal_small"}
      action_id="end_turn", targets=[], data={}
    """
    actor_id: str
    action_id: str
    targets: Sequence[str] = ()
    data: Mapping[str, object] = field(default_factory=dict)