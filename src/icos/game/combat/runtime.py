from __future__ import annotations

from dataclasses import dataclass, field

from icos.game.ecs import ECSRegistry, EncounterComponent, PositionComponent, SystemRegistry
from icos.game.effects import (
    AbilityDefinition,
    ApplyConditionEffect,
    DamageEffect,
    HealEffect,
    ModifyStatEffect,
    MoveEffect,
    RollCheckEffect,
)
from icos.game.events import EventBus
from icos.game.rules.dice import Dice
from icos.game.runtime.actor import ActorBlueprint
from icos.game.runtime.ecs import ENCOUNTER_ENTITY_ID, build_world_from_actor_blueprints
from icos.game.systems import (
    actor_snapshot,
    action_resolution_system,
    alive_teams,
    ai_action_selection_system,
    apply_event_to_world,
    condition_tick_system,
    initiative_system,
    living_enemies,
    turn_advance_system,
    turn_start_system,
)
from icos.tact.core.actions import ActionRequest
from icos.tact.core.state import EncounterState
from icos.tact.events.types import Event


@dataclass
class CombatEcsRuntime:
    encounter_entity: str = ENCOUNTER_ENTITY_ID
    ability_catalog: dict[str, AbilityDefinition] = field(default_factory=dict)

    _initiative_systems: SystemRegistry = field(init=False, repr=False)
    _before_turn_systems: SystemRegistry = field(init=False, repr=False)
    _action_systems: SystemRegistry = field(init=False, repr=False)
    _turn_end_systems: SystemRegistry = field(init=False, repr=False)
    _ai_systems: SystemRegistry = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._initiative_systems = SystemRegistry()
        self._initiative_systems.register("initiative", initiative_system, order=10)

        self._before_turn_systems = SystemRegistry()
        self._before_turn_systems.register("turn_start", turn_start_system, order=10)
        self._before_turn_systems.register("condition_tick", condition_tick_system, order=20)

        self._action_systems = SystemRegistry()
        self._action_systems.register("action_resolution", action_resolution_system, order=10)

        self._turn_end_systems = SystemRegistry()
        self._turn_end_systems.register("turn_advance", turn_advance_system, order=10)

        self._ai_systems = SystemRegistry()
        self._ai_systems.register("ai_action_selection", ai_action_selection_system, order=10)

    def bootstrap(self, state: EncounterState[ActorBlueprint], *, dice: Dice) -> list[Event]:
        world = self._world_from_state(state)
        bus = EventBus()
        self._initiative_systems.run(
            world,
            bus,
            context={
                "dice": dice,
                "encounter_entity": self.encounter_entity,
            },
        )
        return bus.drain()

    def before_turn(self, state: EncounterState[ActorBlueprint], actor_id: str, *, dice: Dice) -> list[Event]:
        world = self.world(state)
        bus = EventBus()
        self._before_turn_systems.run(
            world,
            bus,
            context={
                "dice": dice,
                "actor_id": actor_id,
                "encounter_entity": self.encounter_entity,
            },
        )
        return bus.drain()

    def resolve_action(self, state: EncounterState[ActorBlueprint], action: ActionRequest, *, dice: Dice) -> list[Event]:
        world = self.world(state)
        bus = EventBus()
        self._action_systems.run(
            world,
            bus,
            context={
                "dice": dice,
                "action": action,
                "actor_id": action.actor_id,
                "action_id": action.action_id,
                "encounter_entity": self.encounter_entity,
                "ability_catalog": state.data.get("ability_catalog", {}),
            },
        )
        return bus.drain()

    def advance_turn(self, state: EncounterState[ActorBlueprint], *, dice: Dice) -> list[Event]:
        world = self.world(state)
        bus = EventBus()
        self._turn_end_systems.run(
            world,
            bus,
            context={
                "dice": dice,
                "encounter_entity": self.encounter_entity,
            },
        )
        return bus.drain()

    def apply_event(self, state: EncounterState[ActorBlueprint], event: Event) -> list[Event]:
        world = self.world(state)
        spawned = apply_event_to_world(world, event, encounter_entity=self.encounter_entity)
        self._sync_state_turn_cursor(state, world)
        return spawned

    def state_summary(self, state: EncounterState[ActorBlueprint]) -> dict[str, object]:
        world = self.world(state)
        snapshots = [actor_snapshot(world, actor_id) for actor_id in self.actor_ids(state)]
        snapshots.sort(key=lambda s: s.id)

        return {
            "round": state.round_num,
            "turn_index": state.turn_index,
            "turn_order": list(state.turn_order),
            "actors": [
                {
                    "id": snap.id,
                    "team": snap.team,
                    "alive": snap.alive,
                    "flags": list(snap.flags),
                    "hp": snap.hp,
                    "max_hp": snap.max_hp,
                    "conditions": dict(snap.conditions),
                }
                for snap in snapshots
            ],
        }

    def actor_name(self, state: EncounterState[ActorBlueprint], actor_id: str) -> str:
        return actor_snapshot(self.world(state), actor_id).name

    def actor_is_alive(self, state: EncounterState[ActorBlueprint], actor_id: str) -> bool:
        return actor_snapshot(self.world(state), actor_id).alive

    def actor_ids(self, state: EncounterState[ActorBlueprint]) -> list[str]:
        world = self.world(state)
        encounter = world.get_component(self.encounter_entity, EncounterComponent)
        if encounter.turn_order:
            return list(encounter.turn_order)
        return [a.id for a in state.actors]

    def legal_actions(self, state: EncounterState[ActorBlueprint], actor_id: str) -> list[ActionRequest]:
        snap = actor_snapshot(self.world(state), actor_id)
        if not snap.alive:
            return []

        if any(name in snap.conditions for name in ("stunned", "paralyzed", "unconscious", "incapacitated")):
            return [ActionRequest(actor_id=actor_id, action_id="wait")]

        actions: list[ActionRequest] = []

        for enemy in living_enemies(self.world(state), actor_id):
            actions.append(
                ActionRequest(
                    actor_id=actor_id,
                    action_id="attack",
                    targets=(enemy.id,),
                    data={"attack_index": 0},
                )
            )

        catalog = state.data.get("ability_catalog")
        if isinstance(catalog, dict):
            for ability_id in snap.ability_ids:
                ability = catalog.get(ability_id)
                target_rule = getattr(ability, "target_rule", "target")
                if str(target_rule).strip().lower() in {"self", "caster", "source"}:
                    actions.append(
                        ActionRequest(
                            actor_id=actor_id,
                            action_id="use_ability",
                            targets=(actor_id,),
                            data={"ability_id": ability_id},
                        )
                    )
                else:
                    for enemy in living_enemies(self.world(state), actor_id):
                        actions.append(
                            ActionRequest(
                                actor_id=actor_id,
                                action_id="use_ability",
                                targets=(enemy.id,),
                                data={"ability_id": ability_id},
                            )
                        )

        actions.append(ActionRequest(actor_id=actor_id, action_id="defend"))

        if snap.heals_remaining > 0 and snap.hp < snap.max_hp:
            actions.append(
                ActionRequest(
                    actor_id=actor_id,
                    action_id="heal",
                    targets=(actor_id,),
                    data={"heal_dice": snap.heal_dice},
                )
            )

        if snap.move_remaining > 0:
            actions.append(
                ActionRequest(
                    actor_id=actor_id,
                    action_id="move",
                    targets=(actor_id,),
                    data={"distance": min(10, snap.move_remaining)},
                )
            )

        actions.append(ActionRequest(actor_id=actor_id, action_id="wait"))
        return actions

    def action_intent(self, state: EncounterState[ActorBlueprint], action: ActionRequest) -> dict[str, object]:
        action_type = _canonical_action_type(action.action_id)
        target_ids = [str(t) for t in action.targets]
        defaults = _default_action_intent(
            actor_id=action.actor_id,
            action_type=action_type,
            target_ids=target_ids,
        )

        try:
            world = self.world(state)
            source = actor_snapshot(world, action.actor_id)
        except Exception:
            return defaults

        predicted_hit_probability = 0.0
        predicted_damage: str | dict[str, object] = "0"
        resource_cost: dict[str, object] = {}
        expected_effects: list[str] = []

        if action_type == "attack" and source.attacks:
            attack_index = _safe_attack_index(action)
            attack = source.attacks[min(attack_index, len(source.attacks) - 1)]
            expected_effects = ["roll_check:attack_bonus", f"damage:{str(attack.damage_type).lower()}"]
            predicted_damage = str(attack.damage_dice)

            if target_ids:
                try:
                    defender = actor_snapshot(world, target_ids[0])
                    bonus = int(attack.attack_bonus + source.attack_bonus_bonus)
                    predicted_hit_probability = _attack_hit_probability(attack_bonus=bonus, target_ac=defender.ac)
                except Exception:
                    predicted_hit_probability = 0.5
            else:
                predicted_hit_probability = 0.0

        elif action_type == "heal":
            heal_dice = str(action.data.get("heal_dice", source.heal_dice))
            predicted_hit_probability = 1.0
            predicted_damage = heal_dice
            resource_cost = {"heals": 1 if source.heals_remaining > 0 else 0}
            expected_effects = ["heal"]

        elif action_type == "move":
            requested = _as_int(action.data.get("distance", 0), default=0)
            allowed = min(abs(requested), max(0, source.move_remaining))
            predicted_hit_probability = 1.0 if allowed > 0 else 0.0
            predicted_damage = "0"
            resource_cost = {"movement": allowed}
            expected_effects = ["move"]

        elif action_type == "defend":
            predicted_hit_probability = 1.0
            predicted_damage = "0"
            expected_effects = ["apply_condition:defending"]

        elif action_type in {"use_ability", "cast_spell"}:
            ability = _lookup_ability(state, action)
            if ability is not None:
                expected_effects = _effect_identifiers(ability)
                predicted_damage = _ability_damage_preview(ability)
                predicted_hit_probability = 0.6 if any(isinstance(effect, RollCheckEffect) for effect in ability.effects) else 1.0
            else:
                predicted_hit_probability = 0.5
                predicted_damage = "0"
                expected_effects = []

        elif action_type == "wait":
            predicted_hit_probability = 1.0
            predicted_damage = "0"
            expected_effects = []

        tactical_context = {
            "distance_to_target": _distance_to_first_target(world, action.actor_id, target_ids),
            "aoe_radius": max(0, _as_int(action.data.get("aoe_radius", 0), default=0)),
            "enemy_cluster_density": _enemy_cluster_density(world, action.actor_id, target_ids),
            "expected_effects": expected_effects,
            "actor_hp_ratio": round(source.hp / max(1, source.max_hp), 4),
            "movement_remaining": int(source.move_remaining),
        }

        return {
            "actor_id": action.actor_id,
            "action_type": action_type,
            "target_ids": target_ids,
            "predicted_hit_probability": round(max(0.0, min(1.0, predicted_hit_probability)), 4),
            "predicted_damage": predicted_damage,
            "resource_cost": resource_cost,
            "tactical_context": tactical_context,
        }

    def choose_ai_action(self, state: EncounterState[ActorBlueprint], actor_id: str) -> tuple[ActionRequest, list[Event]]:
        world = self.world(state)
        bus = EventBus()
        context: dict[str, object] = {"actor_id": actor_id}
        self._ai_systems.run(world, bus, context=context)

        selected = context.get("selected_action")
        if not isinstance(selected, ActionRequest):
            selected = ActionRequest(actor_id=actor_id, action_id="wait")

        return selected, bus.drain()

    def is_over(self, state: EncounterState[ActorBlueprint]) -> bool:
        return len(alive_teams(self.world(state))) <= 1

    def outcome(self, state: EncounterState[ActorBlueprint]) -> str | None:
        teams = alive_teams(self.world(state))
        if len(teams) == 1:
            return next(iter(teams))
        return None

    def world(self, state: EncounterState[ActorBlueprint]) -> ECSRegistry:
        world_obj = state.data.get("ecs_world")
        if not isinstance(world_obj, ECSRegistry):
            raise RuntimeError("ECS world is not initialized. Call init_encounter first.")
        return world_obj

    def _world_from_state(self, state: EncounterState[ActorBlueprint]) -> ECSRegistry:
        world_obj = state.data.get("ecs_world")
        if isinstance(world_obj, ECSRegistry):
            return world_obj

        world = build_world_from_actor_blueprints(list(state.actors))
        state.data["ecs_world"] = world
        state.data["encounter_entity"] = self.encounter_entity
        state.data["ability_catalog"] = dict(self.ability_catalog)
        self._sync_state_turn_cursor(state, world)
        return world

    def _sync_state_turn_cursor(self, state: EncounterState[ActorBlueprint], world: ECSRegistry) -> None:
        encounter = world.get_component(self.encounter_entity, EncounterComponent)
        state.round_num = encounter.round_num
        state.turn_index = encounter.turn_index
        state.turn_order = list(encounter.turn_order)


def _canonical_action_type(action_id: str) -> str:
    token = str(action_id).strip().lower()
    if token in {"cast_spell", "cast"}:
        return "cast_spell"
    if token in {"use_ability", "ability"}:
        return "use_ability"
    if token in {"use_item", "item"}:
        return "use_item"
    if token in {"move", "attack", "defend", "heal", "wait"}:
        return token
    return token or "wait"


def _default_action_intent(*, actor_id: str, action_type: str, target_ids: list[str]) -> dict[str, object]:
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


def _safe_attack_index(action: ActionRequest) -> int:
    idx = _as_int(action.data.get("attack_index", 0), default=0)
    return max(0, idx)


def _attack_hit_probability(*, attack_bonus: int, target_ac: int) -> float:
    hits = 0
    for natural in range(1, 21):
        if natural == 1:
            continue
        if natural == 20 or (natural + int(attack_bonus)) >= int(target_ac):
            hits += 1
    return hits / 20.0


def _lookup_ability(state: EncounterState[ActorBlueprint], action: ActionRequest) -> AbilityDefinition | None:
    ability_id = str(action.data.get("ability_id", "")).strip()
    if not ability_id:
        return None

    catalog = state.data.get("ability_catalog")
    if not isinstance(catalog, dict):
        return None

    ability = catalog.get(ability_id)
    if isinstance(ability, AbilityDefinition):
        return ability
    return None


def _effect_identifiers(ability: AbilityDefinition) -> list[str]:
    out: list[str] = []
    for effect in ability.effects:
        if isinstance(effect, DamageEffect):
            out.append(f"damage:{str(effect.damage_type).lower()}")
        elif isinstance(effect, HealEffect):
            out.append("heal")
        elif isinstance(effect, ApplyConditionEffect):
            out.append(f"apply_condition:{effect.condition}")
        elif isinstance(effect, MoveEffect):
            out.append("move")
        elif isinstance(effect, ModifyStatEffect):
            out.append("modify_stat")
        elif isinstance(effect, RollCheckEffect):
            out.append(f"roll_check:{effect.stat}")
    return out


def _ability_damage_preview(ability: AbilityDefinition) -> str | dict[str, object]:
    damage_specs: list[dict[str, object]] = []
    for effect in ability.effects:
        if isinstance(effect, DamageEffect):
            damage_specs.append({"amount": effect.amount, "damage_type": effect.damage_type})

    if not damage_specs:
        return "0"
    if len(damage_specs) == 1:
        return damage_specs[0]
    return {"segments": damage_specs}


def _distance_to_first_target(world: ECSRegistry, actor_id: str, target_ids: list[str]) -> int | None:
    if not target_ids:
        return None
    if not world.has_component(actor_id, PositionComponent):
        return None
    target_id = target_ids[0]
    if not world.has_component(target_id, PositionComponent):
        return None

    src = world.get_component(actor_id, PositionComponent)
    dst = world.get_component(target_id, PositionComponent)
    return abs(int(src.x) - int(dst.x)) + abs(int(src.y) - int(dst.y))


def _enemy_cluster_density(world: ECSRegistry, actor_id: str, target_ids: list[str]) -> float:
    enemies = living_enemies(world, actor_id)
    if not enemies:
        return 0.0

    anchor_id = target_ids[0] if target_ids else enemies[0].id
    if not world.has_component(anchor_id, PositionComponent):
        return 0.0
    anchor = world.get_component(anchor_id, PositionComponent)

    clustered = 0
    for enemy in enemies:
        if not world.has_component(enemy.id, PositionComponent):
            continue
        pos = world.get_component(enemy.id, PositionComponent)
        distance = abs(int(anchor.x) - int(pos.x)) + abs(int(anchor.y) - int(pos.y))
        if distance <= 10:
            clustered += 1

    return round(clustered / max(1, len(enemies)), 4)


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
