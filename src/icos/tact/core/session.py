from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Mapping, Optional, Protocol, Sequence, TypeVar

from .actions import ActionRequest
from .state import EncounterState
from .types import ActorLike
from ..events import (
    ACTION_APPLIED,
    ACTION_REQUESTED,
    ACTION_RESOLVED,
    ACTION_VALIDATED,
    ENCOUNTER_ENDED,
    ENCOUNTER_STARTED,
    EVENT_SCHEMA_V1,
    TURN_ENDED,
    TURN_SKIPPED,
    TURN_STARTED,
    Event,
)

TActor = TypeVar("TActor", bound=ActorLike)

TActor_contra = TypeVar("TActor_contra", bound=ActorLike, contravariant=True)

EventSink = Callable[[Event], None]


class EncounterController(Protocol, Generic[TActor_contra]):
    def choose_action(self, state: EncounterState[TActor_contra], actor_id: str) -> ActionRequest: ...


class EncounterLoop(Protocol, Generic[TActor_contra]):
    def init_encounter(self, state: EncounterState[TActor_contra]) -> List[Event]: ...
    def before_turn(self, state: EncounterState[TActor_contra], actor_id: str) -> List[Event]: ...
    def resolve_action(self, state: EncounterState[TActor_contra], action: ActionRequest) -> List[Event]: ...
    def is_over(self, state: EncounterState[TActor_contra]) -> bool: ...
    def outcome(self, state: EncounterState[TActor_contra]) -> Optional[str]: ...
    def finalize(self, state: EncounterState[TActor_contra]) -> List[Event]: ...


@dataclass
class EncounterSession(Generic[TActor]):
    """
    Generic encounter runner with lifecycle and deterministic event sequencing.
    """

    def run(
        self,
        loop: EncounterLoop[TActor],
        actors: List[TActor],
        controllers: Mapping[str, EncounterController[TActor]],
        *,
        max_rounds: int = 50,
        on_event: Optional[EventSink] = None,
    ) -> List[Event]:
        state = EncounterState[TActor](actors=actors)
        log: List[Event] = []

        event_seq = 0
        action_seq = 0

        def emit(ev: Event) -> Event:
            nonlocal event_seq
            event_seq += 1

            payload = dict(ev.data)
            payload.setdefault("event_schema", EVENT_SCHEMA_V1)
            payload.setdefault("event_seq", event_seq)
            payload.setdefault("round", state.round_num)
            payload.setdefault("turn_index", state.turn_index)

            canonical = Event(
                type=ev.type,
                actor=ev.actor,
                target=ev.target,
                message="",
                data=payload,
            )

            log.append(canonical)
            if on_event is not None:
                on_event(canonical)
            return canonical

        def process_events(events: List[Event], *, action_id: int | None = None) -> List[Event]:
            queue = list(events)
            emitted: List[Event] = []

            while queue:
                event = queue.pop(0)
                if action_id is not None:
                    event = self._attach_action_context(event, action_id)

                canonical = emit(event)
                emitted.append(canonical)

                for spawned in self._apply_event(loop, state, canonical):
                    queue.append(spawned)

            return emitted

        emit(
            Event(
                type=ENCOUNTER_STARTED,
                data={
                    "phase": "encounter",
                    "status": "started",
                },
            )
        )
        process_events(loop.init_encounter(state))

        while not loop.is_over(state) and state.round_num <= max_rounds:
            actor_id = state.current_actor_id()

            if not self._actor_is_alive(loop, state, actor_id):
                emit(
                    Event(
                        type=TURN_SKIPPED,
                        actor=actor_id,
                        data={
                            "actor_id": actor_id,
                            "reason": "actor_not_alive",
                        },
                    )
                )
                process_events(self._advance_turn(loop, state))
                continue

            emit(
                Event(
                    type=TURN_STARTED,
                    actor=actor_id,
                    data={"actor_id": actor_id},
                )
            )

            process_events(loop.before_turn(state, actor_id))

            controller = controllers.get(actor_id)
            source = "controller" if controller is not None else "default_wait"
            raw_action = (
                controller.choose_action(state, actor_id)
                if controller is not None
                else ActionRequest(actor_id=actor_id, action_id="wait")
            )

            action_seq += 1
            requested_payload = self._build_action_requested_payload(
                loop=loop,
                state=state,
                action=raw_action,
                actor_id=actor_id,
                action_seq=action_seq,
                source=source,
            )
            emit(
                Event(
                    type=ACTION_REQUESTED,
                    actor=actor_id,
                    data=requested_payload,
                )
            )

            action, valid, issues = self._normalize_action(loop, state, actor_id, raw_action)
            validated_payload = self._build_action_validated_payload(
                action=action,
                actor_id=actor_id,
                action_seq=action_seq,
                valid=valid,
                issues=issues,
            )
            emit(
                Event(
                    type=ACTION_VALIDATED,
                    actor=actor_id,
                    data=validated_payload,
                )
            )

            emitted_resolved = process_events(loop.resolve_action(state, action), action_id=action_seq)
            resolved_payload = self._build_action_resolved_payload(
                loop=loop,
                state=state,
                action=action,
                action_seq=action_seq,
                emitted_events=emitted_resolved,
            )
            emit(
                Event(
                    type=ACTION_RESOLVED,
                    actor=actor_id,
                    data=resolved_payload,
                )
            )

            emit(
                Event(
                    type=TURN_ENDED,
                    actor=actor_id,
                    data={
                        "actor_id": actor_id,
                        "action_seq": action_seq,
                    },
                )
            )

            process_events(self._advance_turn(loop, state), action_id=action_seq)
            emit(
                Event(
                    type=ACTION_APPLIED,
                    actor=actor_id,
                    data={
                        "actor_id": actor_id,
                        "action_seq": action_seq,
                        "action_type": self._action_type_for(action.action_id),
                        "state": self._state_summary(loop, state),
                    },
                )
            )

        process_events(loop.finalize(state))

        out = loop.outcome(state)
        emit(
            Event(
                type=ENCOUNTER_ENDED,
                data={
                    "status": "ended",
                    "outcome": out,
                },
            )
        )
        return log

    @staticmethod
    def _attach_action_context(event: Event, action_seq: int) -> Event:
        payload = dict(event.data)
        payload.setdefault("action_seq", action_seq)
        return Event(
            type=event.type,
            actor=event.actor,
            target=event.target,
            message="",
            data=payload,
        )

    @staticmethod
    def _action_to_payload(action: ActionRequest) -> dict[str, object]:
        return {
            "actor_id": action.actor_id,
            "action_id": action.action_id,
            "targets": [str(t) for t in action.targets],
            "data": dict(action.data),
        }

    def _build_action_requested_payload(
        self,
        *,
        loop: EncounterLoop[TActor],
        state: EncounterState[TActor],
        action: ActionRequest,
        actor_id: str,
        action_seq: int,
        source: str,
    ) -> dict[str, object]:
        action_type = self._action_type_for(action.action_id)
        base = self._default_action_requested_payload(
            actor_id=actor_id,
            action_type=action_type,
            target_ids=[str(t) for t in action.targets],
        )
        extras = self._loop_payload(loop, "action_intent", state, action)
        merged = self._merge_action_requested(base, extras)
        merged["action_seq"] = action_seq
        merged["source"] = source
        merged["action"] = self._action_to_payload(action)
        return merged

    def _build_action_validated_payload(
        self,
        *,
        action: ActionRequest,
        actor_id: str,
        action_seq: int,
        valid: bool,
        issues: Sequence[str],
    ) -> dict[str, object]:
        notes = [str(issue) for issue in issues]
        if not valid:
            notes.append("replaced_with_wait")
        return {
            "actor_id": actor_id,
            "action_type": self._action_type_for(action.action_id),
            "validated_target_ids": [str(t) for t in action.targets],
            "notes": notes,
            "action_seq": action_seq,
            "valid": bool(valid),
            "action": self._action_to_payload(action),
        }

    def _build_action_resolved_payload(
        self,
        *,
        loop: EncounterLoop[TActor],
        state: EncounterState[TActor],
        action: ActionRequest,
        action_seq: int,
        emitted_events: Sequence[Event],
    ) -> dict[str, object]:
        summary = self._summarize_action_result(action, emitted_events)
        extras = self._loop_payload(loop, "action_resolution_summary", state, action, list(emitted_events))
        if extras:
            for key, value in extras.items():
                summary[str(key)] = value

        summary["action_seq"] = action_seq
        summary["emitted_event_count"] = len(emitted_events)
        summary["emitted_event_types"] = [event.type for event in emitted_events]
        summary["action"] = self._action_to_payload(action)
        return summary

    @staticmethod
    def _default_action_requested_payload(
        *,
        actor_id: str,
        action_type: str,
        target_ids: list[str],
    ) -> dict[str, object]:
        return {
            "actor_id": actor_id,
            "action_type": action_type,
            "target_ids": list(target_ids),
            "predicted_hit_probability": 0.0,
            "predicted_damage": "0",
            "resource_cost": {},
            "tactical_context": {
                "distance_to_target": None,
                "aoe_radius": 0,
                "enemy_cluster_density": 0.0,
                "expected_effects": [],
            },
        }

    @staticmethod
    def _merge_action_requested(base: dict[str, object], extras: Mapping[str, object]) -> dict[str, object]:
        merged = dict(base)

        actor_id = extras.get("actor_id")
        if isinstance(actor_id, str) and actor_id:
            merged["actor_id"] = actor_id

        action_type = extras.get("action_type")
        if isinstance(action_type, str) and action_type:
            merged["action_type"] = action_type

        target_ids = extras.get("target_ids")
        if isinstance(target_ids, list):
            merged["target_ids"] = [str(v) for v in target_ids]

        hit_prob = extras.get("predicted_hit_probability")
        if isinstance(hit_prob, (int, float)):
            merged["predicted_hit_probability"] = max(0.0, min(1.0, float(hit_prob)))

        predicted_damage = extras.get("predicted_damage")
        if isinstance(predicted_damage, (str, dict, list, int, float)):
            merged["predicted_damage"] = predicted_damage

        resource_cost = extras.get("resource_cost")
        if isinstance(resource_cost, dict):
            merged["resource_cost"] = {str(k): v for k, v in resource_cost.items()}

        tactical_context = extras.get("tactical_context")
        if isinstance(tactical_context, dict):
            merged_ctx = dict(merged["tactical_context"]) if isinstance(merged.get("tactical_context"), dict) else {}
            for key, value in tactical_context.items():
                merged_ctx[str(key)] = value
            merged["tactical_context"] = merged_ctx

        return merged

    def _summarize_action_result(self, action: ActionRequest, emitted_events: Sequence[Event]) -> dict[str, object]:
        action_type = self._action_type_for(action.action_id)
        target_ids = [str(t) for t in action.targets]

        target_map: dict[str, dict[str, object]] = {
            target_id: {
                "target_id": target_id,
                "hit": False,
                "damage": 0,
                "conditions_applied": [],
            }
            for target_id in target_ids
        }

        secondary_effects: list[str] = []
        resource_cost_applied = False
        movement_applied = 0
        has_critical = False
        has_attack_check = False
        has_effect = False

        for event in emitted_events:
            event_type = str(event.type)
            payload = dict(event.data)

            if event_type not in {"action.requested", "action.validated", "action.resolved"}:
                if event_type not in secondary_effects:
                    secondary_effects.append(event_type)

            target_id = event.target or payload.get("target_id")
            if isinstance(target_id, str) and target_id and target_id not in target_map:
                target_map[target_id] = {
                    "target_id": target_id,
                    "hit": False,
                    "damage": 0,
                    "conditions_applied": [],
                }

            if event_type == "check.rolled":
                stat = str(payload.get("stat", "")).strip().lower()
                if stat in {"attack", "attack_bonus"}:
                    has_attack_check = True
                    hit = bool(payload.get("success", False))
                    critical = bool(payload.get("critical", False))
                    has_critical = has_critical or critical
                    if isinstance(target_id, str) and target_id in target_map:
                        target_map[target_id]["hit"] = hit

            if event_type == "damage.applied":
                amount = self._as_int(payload.get("amount"), default=0)
                if isinstance(target_id, str) and target_id in target_map:
                    current_damage = self._as_int(target_map[target_id].get("damage"), default=0)
                    target_map[target_id]["damage"] = current_damage + max(0, amount)
                    if amount > 0:
                        target_map[target_id]["hit"] = True
                has_effect = has_effect or amount > 0

            if event_type == "condition.applied":
                condition = str(payload.get("condition", "")).strip().lower()
                if condition and isinstance(target_id, str) and target_id in target_map:
                    conditions = target_map[target_id].get("conditions_applied")
                    if isinstance(conditions, list) and condition not in conditions:
                        conditions.append(condition)
                        has_effect = True

            if event_type == "movement.applied":
                movement_applied += self._as_int(payload.get("distance"), default=0)
                has_effect = has_effect or movement_applied != 0

            if event_type == "heal.applied":
                amount = self._as_int(payload.get("amount"), default=0)
                has_effect = has_effect or amount > 0
                if bool(payload.get("consume_heal", False)):
                    resource_cost_applied = True

            if event_type == "ability.effect_applied":
                has_effect = True

            if bool(payload.get("resource_cost_applied", False)):
                resource_cost_applied = True

        target_results: list[dict[str, object]] = []
        for target_id in target_ids:
            if target_id in target_map:
                entry = target_map[target_id]
                conditions = entry.get("conditions_applied")
                target_results.append(
                    {
                        "target_id": target_id,
                        "hit": bool(entry.get("hit", False)),
                        "damage": max(0, self._as_int(entry.get("damage"), default=0)),
                        "conditions_applied": sorted({str(v) for v in conditions}) if isinstance(conditions, list) else [],
                    }
                )

        known_targets = set(target_ids)
        extra_targets = sorted(target_id for target_id in target_map if target_id not in known_targets)
        for target_id in extra_targets:
            entry = target_map[target_id]
            conditions = entry.get("conditions_applied")
            target_results.append(
                {
                    "target_id": target_id,
                    "hit": bool(entry.get("hit", False)),
                    "damage": max(0, self._as_int(entry.get("damage"), default=0)),
                    "conditions_applied": sorted({str(v) for v in conditions}) if isinstance(conditions, list) else [],
                }
            )

        if action_type in {"attack", "cast_spell", "use_ability"} and has_attack_check:
            if has_critical:
                result = "crit"
            elif any(bool(entry.get("hit", False)) for entry in target_results):
                result = "hit"
            else:
                result = "miss"
        else:
            result = "success" if has_effect or bool(emitted_events) else "fail"

        return {
            "actor_id": action.actor_id,
            "action_type": action_type,
            "result": result,
            "target_results": target_results,
            "resource_cost_applied": resource_cost_applied,
            "movement_applied": movement_applied,
            "secondary_effects": secondary_effects,
        }

    @staticmethod
    def _loop_payload(
        loop: EncounterLoop[TActor],
        hook_name: str,
        *args: object,
    ) -> dict[str, object]:
        fn = getattr(loop, hook_name, None)
        if not callable(fn):
            return {}

        try:
            out = fn(*args)
        except Exception:
            return {}
        if not isinstance(out, dict):
            return {}

        return {str(k): v for k, v in out.items()}

    @staticmethod
    def _action_type_for(action_id: str) -> str:
        token = str(action_id).strip().lower()
        if token in {"cast_spell", "cast"}:
            return "cast_spell"
        if token in {"use_ability", "ability"}:
            return "use_ability"
        if token in {"use_item", "item"}:
            return "use_item"
        if token in {"attack", "move", "defend", "heal", "wait"}:
            return token
        return token or "wait"

    @staticmethod
    def _as_int(value: object, *, default: int) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def _normalize_action(
        self,
        loop: EncounterLoop[TActor],
        state: EncounterState[TActor],
        actor_id: str,
        action: ActionRequest,
    ) -> tuple[ActionRequest, bool, list[str]]:
        issues: list[str] = []

        action_id = str(action.action_id).strip().lower()
        if not action_id:
            issues.append("missing_action_id")
            action_id = "wait"

        if action.actor_id != actor_id:
            issues.append("actor_mismatch")

        known_ids = set(self._actor_ids(loop, state))
        targets = tuple(str(t) for t in action.targets)
        bad_targets = [t for t in targets if t not in known_ids]
        if bad_targets:
            issues.append(f"unknown_targets:{','.join(sorted(bad_targets))}")

        data = dict(action.data)

        if issues:
            return ActionRequest(actor_id=actor_id, action_id="wait"), False, issues

        return (
            ActionRequest(
                actor_id=actor_id,
                action_id=action_id,
                targets=targets,
                data=data,
            ),
            True,
            [],
        )

    def _apply_event(self, loop: EncounterLoop[TActor], state: EncounterState[TActor], event: Event) -> list[Event]:
        fn = getattr(loop, "apply_event", None)
        if not callable(fn):
            return []

        out = fn(state, event)
        if not isinstance(out, list):
            return []
        return [e for e in out if isinstance(e, Event)]

    def _advance_turn(self, loop: EncounterLoop[TActor], state: EncounterState[TActor]) -> list[Event]:
        fn = getattr(loop, "advance_turn", None)
        if callable(fn):
            out = fn(state)
            if isinstance(out, list):
                return [e for e in out if isinstance(e, Event)]
            return []

        state.advance_turn()
        return []

    def _actor_ids(self, loop: EncounterLoop[TActor], state: EncounterState[TActor]) -> list[str]:
        fn = getattr(loop, "actor_ids", None)
        if callable(fn):
            out = fn(state)
            if isinstance(out, list):
                return [str(v) for v in out]

        if state.turn_order:
            return list(state.turn_order)
        return [a.id for a in state.actors]

    def _actor_is_alive(self, loop: EncounterLoop[TActor], state: EncounterState[TActor], actor_id: str) -> bool:
        fn = getattr(loop, "actor_is_alive", None)
        if callable(fn):
            out = fn(state, actor_id)
            return bool(out)

        try:
            actor = state.get(actor_id)
            return bool(getattr(actor, "alive", True))
        except Exception:
            return True

    def _state_summary(self, loop: EncounterLoop[TActor], state: EncounterState[TActor]) -> dict[str, object]:
        fn = getattr(loop, "state_summary", None)
        if callable(fn):
            out = fn(state)
            if isinstance(out, dict):
                return {str(k): v for k, v in out.items()}

        actors = sorted(state.actors, key=lambda a: a.id)
        return {
            "round": state.round_num,
            "turn_index": state.turn_index,
            "turn_order": list(state.turn_order),
            "actors": [
                {
                    "id": a.id,
                    "team": getattr(a, "team", ""),
                    "alive": bool(getattr(a, "alive", True)),
                    "flags": sorted(getattr(a, "flags", set())),
                }
                for a in actors
            ],
        }
