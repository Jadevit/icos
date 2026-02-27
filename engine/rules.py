# engine/rules.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .dice import Dice
from .models import ActionDeclaration, AttackProfile, Combatant, Event
from .state import CombatState


@dataclass
class RulesEngine:
    dice: Dice

    def roll_initiative(self, combatants: List[Combatant]) -> Tuple[List[str], List[Event]]:
        events: List[Event] = []
        rolls: List[Tuple[int, int, str, str]] = []

        for c in combatants:
            total = self.dice.d20() + c.dex_mod
            rolls.append((total, c.dex_mod, c.id, c.name))
            events.append(
                Event(
                    type="initiative",
                    actor=c.id,
                    message=f"{c.name} rolls initiative: d20+{c.dex_mod} = {total}",
                    data={"total": total, "dex_mod": c.dex_mod},
                )
            )

        rolls.sort(key=lambda x: x[0], reverse=True)
        order = [cid for _, _, cid, _ in rolls]
        return order, events

    def resolve_action(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        if action.type == "attack":
            return self._resolve_attack(state, action)
        if action.type == "defend":
            return self._resolve_defend(state, action)
        if action.type == "heal":
            return self._resolve_heal(state, action)
        if action.type == "wait":
            return self._resolve_wait(state, action)
        raise ValueError(f"Unsupported action type: {action.type!r}")

    def _resolve_defend(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []
        actor.flags.add("defending")
        return [
            Event(
                type="turn_start",
                actor=actor.id,
                message=f"{actor.name} takes a defensive stance (attacks against them have disadvantage until their next turn).",
                data={"flag_added": "defending"},
            )
        ]

    def _resolve_heal(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []

        # v1: simple healing dice, customizable via action.data if you want later
        heal_dice = str(action.data.get("heal_dice", "1d8+2"))
        roll = self.dice.roll(heal_dice)

        before = actor.hp
        actor.hp = min(actor.max_hp, actor.hp + roll.total)
        healed = actor.hp - before

        return [
            Event(
                type="damage",  # later you might add "heal" event type; keeping minimal now
                actor=actor.id,
                message=f"{actor.name} heals for {healed} (rolled {heal_dice} => {roll.total}). HP {before} -> {actor.hp}",
                data={"heal": healed, "hp_before": before, "hp_after": actor.hp, "heal_dice": heal_dice},
            )
        ]

    def _resolve_wait(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []
        return [
            Event(
                type="turn_start",
                actor=actor.id,
                message=f"{actor.name} waits.",
            )
        ]

    def _resolve_attack(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        events: List[Event] = []

        attacker = state.get(action.actor_id)
        if not attacker.alive:
            return events

        if not action.target_ids:
            return events

        defender = state.get(action.target_ids[0])
        if not defender.alive:
            return events

        atk: AttackProfile = attacker.choose_attack(action.attack_index)

        adv_state = "dis" if "defending" in defender.flags else "normal"
        d20, underlying = self.dice.d20_with_adv_state(adv_state)
        total_to_hit = d20 + atk.attack_bonus

        attack_msg = (
            f"{attacker.name} uses {atk.name}: "
            f"d20({', '.join(map(str, underlying))}) -> {d20} + {atk.attack_bonus} = {total_to_hit} "
            f"vs AC {defender.ac}"
        )
        if adv_state == "dis":
            attack_msg += " (DISADVANTAGE)"

        events.append(
            Event(
                type="attack_roll",
                actor=attacker.id,
                target=defender.id,
                message=attack_msg,
                data={
                    "underlying_d20": underlying,
                    "chosen_d20": d20,
                    "attack_bonus": atk.attack_bonus,
                    "total": total_to_hit,
                    "target_ac": defender.ac,
                    "adv_state": adv_state,
                },
            )
        )

        is_crit = d20 == 20
        hit = is_crit or (total_to_hit >= defender.ac)

        if not hit:
            events.append(
                Event(
                    type="miss",
                    actor=attacker.id,
                    target=defender.id,
                    message=f"{attacker.name} misses {defender.name}.",
                )
            )
            return events

        crit_suffix = " (CRIT)" if is_crit else ""
        events.append(
            Event(
                type="hit",
                actor=attacker.id,
                target=defender.id,
                message=f"{attacker.name} hits {defender.name}{crit_suffix}!",
                data={"crit": is_crit},
            )
        )

        if is_crit:
            dmg1 = self.dice.roll(atk.damage_dice)
            dmg2 = self.dice.roll(atk.damage_dice)
            dmg_total = dmg1.total + dmg2.total
            detail = f"{atk.damage_dice} crit => {dmg1.total} + {dmg2.total} = {dmg_total}"
        else:
            dmg = self.dice.roll(atk.damage_dice)
            dmg_total = dmg.total
            detail = f"{atk.damage_dice} => {dmg_total}"

        before = defender.hp
        defender.hp = max(0, defender.hp - dmg_total)

        damage_msg = (
            f"{defender.name} takes {dmg_total} {atk.damage_type} damage ({detail}). " f"HP {before} -> {defender.hp}"
        )
        events.append(
            Event(
                type="damage",
                actor=attacker.id,
                target=defender.id,
                message=damage_msg,
                data={
                    "amount": dmg_total,
                    "damage_type": atk.damage_type,
                    "hp_before": before,
                    "hp_after": defender.hp,
                },
            )
        )

        if defender.hp == 0:
            events.append(
                Event(
                    type="down",
                    actor=attacker.id,
                    target=defender.id,
                    message=f"{defender.name} goes down!",
                )
            )

        return events
