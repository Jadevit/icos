from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.state import EncounterState
from icos.kernel.events.types import Event

from icos.content.defs.condition import ConditionDefinition
from icos.content.defs.creature import MonsterDefinition
from icos.content.defs.entity import GenericEntityDefinition
from icos.content.defs.item import EquipmentDefinition
from icos.content.defs.spell import SpellDefinition
from icos.game.runtime.actor import AttackProfile, Combatant
from icos.game.runtime.instances import equipment_to_equipped_item
from icos.game.runtime.party import EncounterPlan
from icos.game.combat.actions import ActionRegistry
from icos.game.combat.controllers import PlannerConfig, PlannerController, PlayerController
from icos.game.combat.factories import monster_to_combatant
from icos.game.combat.loop import CombatLoop

from .context import DevContext

CommandFn = Callable[[DevContext, List[str]], Optional[str]]
DEFAULT_EVENT_DELAY_SECONDS = 0.35
PACE_PRESETS: Dict[str, float] = {
    "off": 0.0,
    "fast": 0.12,
    "normal": 0.35,
    "slow": 0.65,
    "cinematic": 1.00,
}


@dataclass
class Command:
    name: str
    help: str
    fn: CommandFn


@dataclass
class CommandRegistry:
    commands: Dict[str, Command] = field(default_factory=dict)

    def register(self, name: str, help: str, fn: CommandFn) -> None:
        self.commands[name] = Command(name=name, help=help, fn=fn)

    def run(self, ctx: DevContext, argv: List[str]) -> Optional[str]:
        if not argv:
            return None
        cmd = self.commands.get(argv[0])
        if cmd is None:
            return f"Unknown command: {argv[0]!r}. Try: help"
        return cmd.fn(ctx, argv[1:])

    def list_help(self) -> str:
        lines = ["Commands:"]
        for name in sorted(self.commands):
            lines.append(f"  {name:<12} {self.commands[name].help}")
        lines.append("")
        lines.append("Quick flow:")
        lines.append("  1) endpoints")
        lines.append("  2) ls monsters 10")
        lines.append("  3) load monsters berserker")
        lines.append("  4) play goblin")
        lines.append("  5) pace slow")
        lines.append("  6) enc new / enc add ... / equip ... / cond ... / enc run")
        return "\n".join(lines)


def install_builtin_commands(registry: CommandRegistry) -> None:
    registry.register("help", "Show command help + examples.", lambda _ctx, _args: registry.list_help())

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
    state: EncounterState[Combatant],
    actor: Combatant,
    legal: List[ActionRequest],
) -> ActionRequest:
    heals = f"{actor.heals_remaining} heals left" if actor.heals_remaining > 0 else "no heals"
    print(f"\n{actor.name} ({actor.id}) HP {actor.hp}/{actor.max_hp} | {heals}", flush=True)

    for idx, action in enumerate(legal):
        if action.action_id == "attack" and action.targets:
            target = state.get(action.targets[0]).name
            print(f"{idx}) attack -> {target}", flush=True)
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
                f"hp={actor.hp}/{actor.max_hp} ac={actor.effective_ac} "
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
    actor.set_hp(value)
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
        actor.add_condition(args[2], turns)
        return f"{actor.id} condition set: {args[2].lower()} ({turns} turns)"

    if sub == "clear":
        if len(args) < 3:
            return "Usage: cond clear <actor_id> <name>"
        actor = _find_actor(ctx, args[1])
        if actor is None:
            return f"No actor with id {args[1]!r}."
        actor.clear_condition(args[2])
        return f"{actor.id} condition cleared: {args[2].lower()}"

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
        lines.append(f"  effective_ac={actor.effective_ac}")
        return "\n".join(lines)

    if len(args) < 2:
        return "Usage: equip <actor_id> <equipment_api_index>"

    actor = _find_actor(ctx, args[0])
    if actor is None:
        return f"No actor with id {args[0]!r}."

    equipment = ctx.engine.get_equipment(args[1])
    equipped = equipment_to_equipped_item(equipment)
    actor.equip_item(equipped)

    mods = equipped.modifiers
    return (
        f"{actor.id} equipped {equipment.name} "
        f"(ac+{mods.ac_bonus} atk+{mods.attack_bonus} dmg+{mods.damage_bonus} heal+{mods.heal_bonus}). "
        f"effective_ac={actor.effective_ac}"
    )


def _add_default_player(ctx: DevContext, *, name: str = "Hero") -> Combatant:
    if ctx.encounter is None:
        raise RuntimeError("No encounter initialized")

    cid = f"party:{name.lower()}"
    hero = Combatant(
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
) -> Combatant:
    if ctx.encounter is None:
        raise RuntimeError("No encounter initialized")

    monster_def = ctx.engine.get_monster(api_index)
    if heals is None:
        heals = _default_enemy_heals(monster_def) if team == "enemies" else 0

    monster = monster_to_combatant(
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
        if event.message:
            print(event.message, flush=True)
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


def _find_actor(ctx: DevContext, actor_id: str) -> Combatant | None:
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
    if t in ("attack_roll", "hit", "miss", "damage", "heal", "down", "defend"):
        return base * 1.0
    return base * 0.75


def _pace_label(delay: float) -> str:
    for name, value in PACE_PRESETS.items():
        if abs(delay - value) < 1e-6:
            return name
    return "custom"


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
