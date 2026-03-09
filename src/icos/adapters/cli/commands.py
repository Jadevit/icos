from __future__ import annotations

import json
import sqlite3
import time
from typing import Dict, List, Optional

from icos.tact.core.actions import ActionRequest
from icos.tact.core.state import EncounterState
from icos.tact.devtools import CommandRegistry, install_tact_commands
from icos.tact.events.types import Event

from icos.content.defs.condition import ConditionDefinition
from icos.content.defs.creature import MonsterDefinition
from icos.content.defs.entity import GenericEntityDefinition
from icos.content.defs.item import EquipmentDefinition
from icos.content.defs.spell import SpellDefinition
from icos.game.runtime.actor import AttackProfile, ActorBlueprint
from icos.game.runtime.instances import equipment_to_equipped_item
from icos.game.runtime.party import EncounterPlan
from icos.game.systems import actor_snapshot
from icos.game.combat.actions import ActionRegistry
from icos.game.combat.controllers import PlannerConfig, PlannerController, PlayerController
from icos.game.combat.factories import monster_to_actor_blueprint
from icos.game.combat.loop import CombatLoop

from .context import DevContext

DEFAULT_EVENT_DELAY_SECONDS = 0.35
PACE_PRESETS: Dict[str, float] = {
    "off": 0.0,
    "fast": 0.12,
    "normal": 0.35,
    "slow": 0.65,
    "cinematic": 1.00,
}

def install_builtin_commands(registry: CommandRegistry[DevContext]) -> None:
    registry.quick_flow = [
        "endpoints",
        "ls monsters 10",
        "load monsters berserker",
        "play goblin",
        "pace slow",
        "enc new / enc add ... / equip ... / cond ... / enc run",
    ]
    install_tact_commands(registry)

    registry.register("ensure_codex", "Build bundles + codex if needed.", _cmd_ensure_codex)
    registry.register("endpoints", "List all DB endpoints with entity counts.", _cmd_endpoints)
    registry.register("ls", "List entities in an endpoint: ls <endpoint> [limit]", _cmd_ls)
    registry.register("load", "Load one entity: load <endpoint> <api_index> [raw]", _cmd_load)
    registry.register("find", "Search ids/names: find <text> [limit]", _cmd_find)

    registry.register("play", "Start immediate playable battle: play [monster_api_index]", _cmd_play)
    registry.register("enc", "Encounter commands: enc new|add|run [replay=...]|reset|list", _cmd_enc)
    registry.register("pace", "Set combat text pace: pace [off|fast|normal|slow|cinematic|seconds]", _cmd_pace)
    registry.register("hp", "HP commands: hp set <actor_id> <value>", _cmd_hp)
    registry.register("cond", "Condition commands: cond set|clear|list ...", _cmd_cond)
    registry.register("equip", "Equip commands: equip <actor_id> <equipment_api_index> | equip list <actor_id>", _cmd_equip)


def _prompt_cli(
    state: EncounterState[ActorBlueprint],
    actor: object,
    legal: List[ActionRequest],
) -> ActionRequest:
    actor_id = str(getattr(actor, "id"))
    actor_name = str(getattr(actor, "name"))
    actor_hp = int(getattr(actor, "hp"))
    actor_max_hp = int(getattr(actor, "max_hp"))
    heals_remaining = int(getattr(actor, "heals_remaining", 0))
    heals = f"{heals_remaining} heals left" if heals_remaining > 0 else "no heals"
    print(f"\n{actor_name} ({actor_id}) HP {actor_hp}/{actor_max_hp} | {heals}", flush=True)

    for idx, action in enumerate(legal):
        if action.action_id == "attack" and action.targets:
            target = _actor_name_from_state(state, str(action.targets[0]))
            print(f"{idx}) attack -> {target}", flush=True)
        elif action.action_id == "use_ability":
            ability_id = str(action.data.get("ability_id", "ability"))
            if action.targets:
                target = _actor_name_from_state(state, str(action.targets[0]))
                print(f"{idx}) use_ability {ability_id} -> {target}", flush=True)
            else:
                print(f"{idx}) use_ability {ability_id}", flush=True)
        else:
            print(f"{idx}) {action.action_id}", flush=True)

    while True:
        choice = input("Choose action # > ").strip()
        if choice.isdigit():
            i = int(choice)
            if 0 <= i < len(legal):
                return legal[i]
        print("Invalid choice.", flush=True)


def _cmd_ensure_codex(ctx: DevContext, _args: List[str]) -> str:
    ctx.engine.ensure_codex()
    return "Codex ensured."


def _cmd_endpoints(ctx: DevContext, _args: List[str]) -> str:
    counts = ctx.engine.count_entities_by_endpoint()
    if not counts:
        return "No endpoints found."

    lines = ["Endpoints:"]
    for endpoint, count in counts.items():
        lines.append(f"  {endpoint:<22} {count:>5}")
    return "\n".join(lines)


def _cmd_ls(ctx: DevContext, args: List[str]) -> str:
    if not args:
        return "Usage: ls <endpoint> [limit]"

    endpoint = args[0]
    limit = _parse_int(args[1]) if len(args) >= 2 else 20
    if limit is None or limit <= 0:
        return "Invalid limit."

    try:
        entities = ctx.engine.list_entities(endpoint, limit=limit)
    except Exception as exc:
        return f"ERROR: {exc}"

    if not entities:
        return f"No entities for endpoint {endpoint!r}."

    lines = [f"{endpoint} ({len(entities)}):"]
    for entity in entities:
        api_index = getattr(entity, "api_index", "")
        name = getattr(entity, "name", "")
        lines.append(f"  {api_index:<24} {name}")
    return "\n".join(lines)


def _cmd_load(ctx: DevContext, args: List[str]) -> str:
    if len(args) < 2:
        return "Usage: load <endpoint> <api_index> [raw]"

    endpoint, api_index = args[0], args[1]
    raw_mode = len(args) >= 3 and args[2].lower() in {"raw", "--raw", "json"}

    try:
        entity = ctx.engine.get_entity(endpoint, api_index)
    except Exception as exc:
        return f"ERROR: {exc}"

    if raw_mode:
        raw = getattr(entity, "raw_json", None)
        if isinstance(raw, dict):
            return json.dumps(raw, indent=2, sort_keys=True)

    return _format_entity_summary(entity)


def _cmd_find(ctx: DevContext, args: List[str]) -> str:
    if not args:
        return "Usage: find <text> [limit]"

    needle = args[0].lower()
    limit = _parse_int(args[1]) if len(args) >= 2 else 50
    if limit is None or limit <= 0:
        return "Invalid limit."

    db = ctx.engine.paths.abs(ctx.engine.paths.codex_db)
    con = sqlite3.connect(db.as_posix())
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT endpoint, api_index, COALESCE(name, '') "
            "FROM entities WHERE lower(id) LIKE ? OR lower(name) LIKE ? "
            "ORDER BY endpoint, api_index LIMIT ?",
            (f"%{needle}%", f"%{needle}%", limit),
        )
        rows = cur.fetchall()
    finally:
        con.close()

    if not rows:
        return "No matches."

    lines = [f"Matches ({len(rows)}):"]
    for endpoint, api_index, name in rows:
        lines.append(f"  {endpoint}:{api_index:<24} {name}")
    return "\n".join(lines)


def _cmd_play(ctx: DevContext, args: List[str]) -> str:
    monster_api_index = args[0] if args else "goblin"

    ctx.encounter = EncounterPlan()
    _add_default_player(ctx)

    try:
        _add_monster(ctx, monster_api_index, team="enemies")
    except Exception:
        fallback = "berserker"
        _add_monster(ctx, fallback, team="enemies")
        monster_api_index = fallback

    _run_encounter(ctx)
    return f"Playable encounter finished (enemy={monster_api_index})."


def _cmd_enc(ctx: DevContext, args: List[str]) -> str:
    if not args:
        return "Usage: enc new|add|run [replay=<path>]|reset|list"

    sub = args[0]

    if sub == "new":
        ctx.encounter = EncounterPlan()
        return "Encounter created."

    if sub == "reset":
        ctx.encounter = None
        return "Encounter cleared."

    if sub == "list":
        if ctx.encounter is None:
            return "No active encounter."

        lines = ["Actors:"]
        for actor in ctx.encounter.actors:
            cond = ",".join(f"{k}:{v}" for k, v in sorted(actor.conditions.items())) or "-"
            lines.append(
                f"  {actor.id:<18} {actor.name:<18} team={actor.team} "
                f"hp={actor.hp}/{actor.max_hp} ac={_effective_ac(actor)} "
                f"heals={actor.heals_remaining} cond={cond}"
            )
        return "\n".join(lines)

    if sub == "add":
        if ctx.encounter is None:
            return "No active encounter. Run: enc new"

        if len(args) < 2:
            return "Usage: enc add pc <name> | enc add monster <api_index> [team=...] [hp=..] [ac=..] [heals=..]"

        kind = args[1]
        if kind == "pc":
            name = args[2] if len(args) >= 3 else "Hero"
            hero = _add_default_player(ctx, name=name)
            return f"Added PC {hero.id}."

        if kind == "monster":
            if len(args) < 3:
                return "Usage: enc add monster <api_index> [team=...] [hp=..] [ac=..] [heals=..]"

            api_index = args[2]
            kv = _parse_kv(args[3:])
            team = kv.get("team", "enemies")
            hp = _parse_int(kv.get("hp"))
            ac = _parse_int(kv.get("ac"))
            heals = _parse_int(kv.get("heals"))

            monster = _add_monster(
                ctx,
                api_index,
                team=team,
                hp=hp,
                ac=ac,
                heals=heals,
            )
            return f"Added monster {monster.id}."

        return f"Unknown add kind: {kind!r} (use pc|monster)"

    if sub == "run":
        if ctx.encounter is None:
            return "No active encounter. Run: enc new"
        kv = _parse_kv(args[1:])
        replay_out = kv.get("replay")
        _run_encounter(ctx, replay_out=replay_out)
        return f"Encounter finished.{f' Replay saved: {replay_out}' if replay_out else ''}"

    return f"Unknown enc subcommand: {sub!r}"


def _cmd_hp(ctx: DevContext, args: List[str]) -> str:
    if len(args) != 3 or args[0] != "set":
        return "Usage: hp set <actor_id> <value>"
    if ctx.encounter is None:
        return "No active encounter."

    actor_id = args[1]
    value = _parse_int(args[2])
    if value is None:
        return "Invalid hp value."

    actor = next((a for a in ctx.encounter.actors if a.id == actor_id), None)
    if actor is None:
        return f"No actor with id {actor_id!r}."

    before = actor.hp
    _set_actor_hp(actor, value)
    return f"{actor.id} HP {before} -> {actor.hp}"


def _cmd_pace(ctx: DevContext, args: List[str]) -> str:
    if not args:
        delay = _base_event_delay(ctx)
        return (
            f"Current pace: {_pace_label(delay)} ({delay:.2f}s/event). "
            "Usage: pace <off|fast|normal|slow|cinematic|seconds>"
        )

    token = args[0].strip().lower()
    if token in PACE_PRESETS:
        delay = PACE_PRESETS[token]
    else:
        try:
            delay = float(token)
        except ValueError:
            valid = ", ".join(PACE_PRESETS.keys())
            return f"Invalid pace value {args[0]!r}. Use one of [{valid}] or a numeric seconds value."

        if delay < 0.0 or delay > 5.0:
            return "Numeric pace must be between 0.0 and 5.0 seconds."

    ctx.vars["event_delay"] = delay
    return f"Pace set to {_pace_label(delay)} ({delay:.2f}s/event)."

def _cmd_cond(ctx: DevContext, args: List[str]) -> str:
    if not args:
        return "Usage: cond set <actor_id> <name> [turns] | cond clear <actor_id> <name> | cond list <actor_id>"
    if ctx.encounter is None:
        return "No active encounter."

    sub = args[0]
    if sub == "set":
        if len(args) < 3:
            return "Usage: cond set <actor_id> <name> [turns]"
        actor = _find_actor(ctx, args[1])
        if actor is None:
            return f"No actor with id {args[1]!r}."
        turns = _parse_int(args[3]) if len(args) >= 4 else 2
        turns = max(1, turns or 2)
        cond = args[2].strip().lower()
        if not cond:
            return "Condition name cannot be empty."
        actor.conditions[cond] = max(actor.conditions.get(cond, 0), turns)
        return f"{actor.id} condition set: {cond} ({turns} turns)"

    if sub == "clear":
        if len(args) < 3:
            return "Usage: cond clear <actor_id> <name>"
        actor = _find_actor(ctx, args[1])
        if actor is None:
            return f"No actor with id {args[1]!r}."
        cond = args[2].strip().lower()
        if cond:
            actor.conditions.pop(cond, None)
        return f"{actor.id} condition cleared: {cond}"

    if sub == "list":
        if len(args) < 2:
            return "Usage: cond list <actor_id>"
        actor = _find_actor(ctx, args[1])
        if actor is None:
            return f"No actor with id {args[1]!r}."
        if not actor.conditions:
            return f"{actor.id} has no conditions."
        parts = [f"{name}({turns})" for name, turns in sorted(actor.conditions.items())]
        return f"{actor.id} conditions: " + ", ".join(parts)

    return "Usage: cond set|clear|list ..."


def _cmd_equip(ctx: DevContext, args: List[str]) -> str:
    if not args:
        return "Usage: equip <actor_id> <equipment_api_index> | equip list <actor_id>"
    if ctx.encounter is None:
        return "No active encounter."

    if args[0] == "list":
        if len(args) < 2:
            return "Usage: equip list <actor_id>"
        actor = _find_actor(ctx, args[1])
        if actor is None:
            return f"No actor with id {args[1]!r}."
        if not actor.inventory.items:
            return f"{actor.id} has no equipped items."
        lines = [f"{actor.id} equipped:"]
        for item in actor.inventory.items:
            m = item.modifiers
            lines.append(
                f"  {item.api_index:<22} {item.name} "
                f"(ac+{m.ac_bonus} atk+{m.attack_bonus} dmg+{m.damage_bonus} heal+{m.heal_bonus})"
            )
        lines.append(f"  effective_ac={_effective_ac(actor)}")
        return "\n".join(lines)

    if len(args) < 2:
        return "Usage: equip <actor_id> <equipment_api_index>"

    actor = _find_actor(ctx, args[0])
    if actor is None:
        return f"No actor with id {args[0]!r}."

    equipment = ctx.engine.get_equipment(args[1])
    equipped = equipment_to_equipped_item(equipment)
    actor.inventory.equip(equipped)

    mods = equipped.modifiers
    return (
        f"{actor.id} equipped {equipment.name} "
        f"(ac+{mods.ac_bonus} atk+{mods.attack_bonus} dmg+{mods.damage_bonus} heal+{mods.heal_bonus}). "
        f"effective_ac={_effective_ac(actor)}"
    )


def _add_default_player(ctx: DevContext, *, name: str = "Hero") -> ActorBlueprint:
    if ctx.encounter is None:
        raise RuntimeError("No encounter initialized")

    cid = f"party:{name.lower()}"
    hero = ActorBlueprint(
        id=cid,
        name=name,
        team="party",
        ac=16,
        max_hp=20,
        hp=20,
        dex=12,
        attacks=[
            AttackProfile(
                name="Longsword",
                attack_bonus=5,
                damage_dice="1d8+3",
                damage_type="Slashing",
            )
        ],
        abilities=["second-wind"],
        heals_remaining=3,
        heal_dice="1d8+2",
    )

    player = PlayerController(registry=ActionRegistry(), prompt=_prompt_cli)
    ctx.encounter.add(hero, controller=player)
    return hero


def _add_monster(
    ctx: DevContext,
    api_index: str,
    *,
    team: str = "enemies",
    hp: int | None = None,
    ac: int | None = None,
    heals: int | None = None,
) -> ActorBlueprint:
    if ctx.encounter is None:
        raise RuntimeError("No encounter initialized")

    monster_def = ctx.engine.get_monster(api_index)
    if heals is None:
        heals = _default_enemy_heals(monster_def) if team == "enemies" else 0

    monster = monster_to_actor_blueprint(
        monster_def,
        team=team,
        instance_id=f"{team}:{api_index}_{len(ctx.encounter.actors) + 1}",
        max_hp_override=hp,
        ac_override=ac,
        heals_remaining=heals,
        heal_dice="1d6+1",
    )

    ai = PlannerController(
        registry=ActionRegistry(),
        config=PlannerConfig(rollouts=80, epsilon=0.02, seed=ctx.engine.seed),
    )
    ctx.encounter.add(monster, controller=ai)
    return monster


def _run_encounter(ctx: DevContext, *, replay_out: str | None = None) -> None:
    if ctx.encounter is None:
        raise RuntimeError("No active encounter")

    def print_event(event: Event) -> None:
        printed = False

        gameplay_line = _format_gameplay_text(ctx, event)
        if gameplay_line:
            print(gameplay_line, flush=True)
            printed = True

        if ctx.verbose_events:
            print(_format_event_debug(event), flush=True)
            printed = True

        if printed:
            delay = _event_delay_for(ctx, event)
            if delay > 0.0:
                time.sleep(delay)

    ctx.encounter.on_event = print_event

    loop = CombatLoop(ctx.engine.dice)
    ctx.engine.run_encounter(
        loop=loop,
        actors=ctx.encounter.actors,
        controllers=ctx.encounter.controllers,
        max_rounds=ctx.encounter.max_rounds,
        on_event=ctx.encounter.on_event,
        replay_out=replay_out,
    )


def _format_entity_summary(entity: object) -> str:
    if isinstance(entity, MonsterDefinition):
        ac_entries = []
        for ac in entity.armor_class:
            src = ", ".join(a.name for a in ac.armor) if ac.armor else ""
            ac_entries.append(f"{ac.value} {ac.ac_type} {f'[{src}]' if src else ''}".strip())

        attack_lines = []
        for action in entity.actions:
            dmg = ", ".join(d.damage_dice for d in action.damages if d.damage_dice)
            if action.attack_bonus is not None:
                attack_lines.append(f"{action.name} (+{action.attack_bonus}) {dmg}".strip())

        return "\n".join(
            [
                f"{entity.id} | {entity.name}",
                f"type={entity.creature_type} subtype={entity.subtype} size={entity.size} alignment={entity.alignment}",
                f"CR={entity.challenge_rating} XP={entity.xp} PB={entity.proficiency_bonus}",
                f"HP={entity.hit_points} ({entity.hit_dice})  AC={'; '.join(ac_entries) if ac_entries else 'unknown'}",
                (
                    "stats="
                    f"STR {entity.abilities.strength} DEX {entity.abilities.dexterity} CON {entity.abilities.constitution} "
                    f"INT {entity.abilities.intelligence} WIS {entity.abilities.wisdom} CHA {entity.abilities.charisma}"
                ),
                f"speed={entity.speed.values}",
                f"attacks={attack_lines if attack_lines else '[]'}",
                f"special={[a.name for a in entity.special_abilities]}",
                f"url={entity.url}",
            ]
        )

    if isinstance(entity, EquipmentDefinition):
        return "\n".join(
            [
                f"{entity.id} | {entity.name}",
                f"category={entity.equipment_category.name if entity.equipment_category else ''} "
                f"gear={entity.gear_category.name if entity.gear_category else ''}",
                f"armor_category={entity.armor_category} weapon_category={entity.weapon_category} range={entity.weapon_range}",
                f"damage={entity.damage_dice} {entity.damage_type.name if entity.damage_type else ''}",
                f"ac_base={entity.armor_class_base} dex_bonus={entity.armor_class_dex_bonus} max_bonus={entity.armor_class_max_bonus}",
                f"cost={entity.cost_quantity} {entity.cost_unit} weight={entity.weight}",
                f"properties={[p.name for p in entity.properties]}",
            ]
        )

    if isinstance(entity, SpellDefinition):
        return "\n".join(
            [
                f"{entity.id} | {entity.name}",
                f"level={entity.level} school={entity.school.name if entity.school else ''}",
                f"casting_time={entity.casting_time} range={entity.range} duration={entity.duration}",
                f"ritual={entity.ritual} concentration={entity.concentration}",
                f"components={list(entity.components)} material={entity.material}",
                f"damage_at_slot_level={entity.damage_at_slot_level}",
                f"damage_at_character_level={entity.damage_at_character_level}",
            ]
        )

    if isinstance(entity, ConditionDefinition):
        return "\n".join(
            [
                f"{entity.id} | {entity.name}",
                f"desc={list(entity.desc[:2])}{' ...' if len(entity.desc) > 2 else ''}",
                f"url={entity.url}",
            ]
        )

    if isinstance(entity, GenericEntityDefinition):
        keys = sorted(entity.raw_json.keys())
        preview = list(entity.desc[:2])
        return "\n".join(
            [
                f"{entity.id} | {entity.name}",
                f"endpoint={entity.endpoint} api_index={entity.api_index}",
                f"keys={keys}",
                f"desc={preview}{' ...' if len(entity.desc) > 2 else ''}",
                f"url={entity.url}",
            ]
        )

    return repr(entity)


def _find_actor(ctx: DevContext, actor_id: str) -> ActorBlueprint | None:
    if ctx.encounter is None:
        return None
    return next((a for a in ctx.encounter.actors if a.id == actor_id), None)


def _default_enemy_heals(monster: MonsterDefinition) -> int:
    cr = monster.challenge_rating
    if cr >= 10:
        return 3
    if cr >= 5:
        return 2
    return 1


def _base_event_delay(ctx: DevContext) -> float:
    val = ctx.vars.get("event_delay")
    if isinstance(val, (int, float)):
        return max(0.0, float(val))
    ctx.vars["event_delay"] = DEFAULT_EVENT_DELAY_SECONDS
    return DEFAULT_EVENT_DELAY_SECONDS


def _event_delay_for(ctx: DevContext, event: Event) -> float:
    base = _base_event_delay(ctx)
    if base <= 0.0:
        return 0.0

    t = event.type
    if t in ("encounter.started", "encounter.ended", "combat_start", "combat_end", "turn.started", "turn_start"):
        return base * 1.35
    if t in (
        "attack_roll",
        "hit",
        "miss",
        "damage",
        "heal",
        "down",
        "defend",
        "attack.started",
        "ability.used",
        "check.rolled",
        "damage.applied",
        "heal.applied",
        "hp.changed",
        "entity.died",
    ):
        return base * 1.0
    return base * 0.75


def _format_event_debug(event: Event) -> str:
    payload = {
        "type": event.type,
        "actor_id": event.actor,
        "target_id": event.target,
        "data": dict(event.data),
    }
    return json.dumps(payload, sort_keys=True)


def _format_gameplay_text(ctx: DevContext, event: Event) -> str | None:
    data = dict(event.data)
    actor_id = event.actor if isinstance(event.actor, str) else _as_str(data.get("actor_id"))
    target_id = event.target if isinstance(event.target, str) else _as_str(data.get("target_id"))
    actor_name = _actor_label(ctx, actor_id)
    target_name = _actor_label(ctx, target_id)

    match event.type:
        case "encounter.started":
            return "Encounter begins."
        case "initiative.rolled":
            total = _as_int(data.get("total"), default=0)
            return f"{actor_name} rolls initiative ({total})."
        case "turn.order_set":
            order = data.get("turn_order")
            if isinstance(order, list) and order:
                labels = " -> ".join(_actor_label(ctx, _as_str(v)) for v in order if _as_str(v))
                if labels:
                    return f"Turn order: {labels}"
            return None
        case "turn.started":
            round_num = _as_int(data.get("round"), default=0)
            return f"\nRound {round_num}: {actor_name}'s turn."
        case "turn.skipped":
            reason = _as_str(data.get("reason")) or "unavailable"
            return f"{actor_name} is skipped ({reason})."
        case "action.requested":
            action_type = _as_str(data.get("action_type")) or "action"
            targets = data.get("target_ids")
            if isinstance(targets, list) and targets:
                named_targets = ", ".join(_actor_label(ctx, _as_str(t)) for t in targets if _as_str(t))
                if named_targets:
                    return f"{actor_name} declares {action_type} -> {named_targets}."
            return f"{actor_name} declares {action_type}."
        case "action.validated":
            notes = data.get("notes")
            if isinstance(notes, list) and notes:
                return f"Validation notes: {', '.join(str(n) for n in notes)}"
            return None
        case "check.rolled":
            stat = _as_str(data.get("stat")) or "check"
            total = _as_int(data.get("total"), default=0)
            dc = _as_int(data.get("dc"), default=0)
            success = bool(data.get("success", False))
            critical = bool(data.get("critical", False))
            if critical:
                return f"{actor_name} lands a critical {stat} ({total} vs DC {dc})."
            verdict = "succeeds" if success else "fails"
            return f"{actor_name} {verdict} {stat} ({total} vs DC {dc})."
        case "damage.applied":
            amount = _as_int(data.get("amount"), default=0)
            damage_type = _as_str(data.get("damage_type")) or "damage"
            return f"{target_name} takes {amount} {damage_type.lower()} damage."
        case "heal.applied":
            amount = _as_int(data.get("amount"), default=0)
            return f"{target_name} heals {amount} HP."
        case "hp.changed":
            before = _as_int(data.get("hp_before"), default=0)
            after = _as_int(data.get("hp_after"), default=0)
            return f"{target_name} HP: {before} -> {after}"
        case "entity.died":
            return f"{target_name} falls."
        case "condition.applied":
            condition = _as_str(data.get("condition")) or "condition"
            duration = _as_int(data.get("duration"), default=1)
            return f"{target_name} gains {condition} ({duration} turns)."
        case "condition.expired":
            condition = _as_str(data.get("condition")) or "condition"
            return f"{actor_name} is no longer {condition}."
        case "movement.applied":
            distance = _as_int(data.get("distance"), default=0)
            return f"{target_name} moves {distance} ft."
        case "heal.failed":
            return f"{actor_name} cannot heal right now."
        case "action.resolved":
            result = _as_str(data.get("result")) or "resolved"
            return f"{actor_name} action result: {result}."
        case "encounter.ended":
            outcome = _as_str(data.get("outcome"))
            if outcome:
                return f"Encounter ends. Winner: {outcome}."
            return "Encounter ends."
        case _:
            return None


def _pace_label(delay: float) -> str:
    for name, value in PACE_PRESETS.items():
        if abs(delay - value) < 1e-6:
            return name
    return "custom"


def _set_actor_hp(actor: ActorBlueprint, value: int) -> None:
    actor.hp = max(0, min(actor.max_hp, int(value)))
    actor.alive = actor.hp > 0


def _effective_ac(actor: ActorBlueprint) -> int:
    return max(1, int(actor.ac) + int(actor.inventory.modifiers.ac_bonus))


def _actor_name_from_state(state: EncounterState[ActorBlueprint], actor_id: str) -> str:
    world = state.data.get("ecs_world")
    if world is not None:
        try:
            return actor_snapshot(world, actor_id).name
        except Exception:
            pass

    try:
        return state.get(actor_id).name
    except Exception:
        return actor_id


def _actor_label(ctx: DevContext, actor_id: str | None) -> str:
    if not actor_id:
        return "Unknown"
    if ctx.encounter is None:
        return actor_id
    actor = next((a for a in ctx.encounter.actors if a.id == actor_id), None)
    if actor is None:
        return actor_id
    duplicate_name = sum(1 for a in ctx.encounter.actors if a.name == actor.name) > 1
    if duplicate_name:
        return f"{actor.name} ({actor_id})"
    return actor.name


def _parse_kv(parts: List[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip().lower()] = value.strip()
    return out


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)
