from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from icos.kernel.core.actions import ActionRequest
from icos.kernel.core.state import EncounterState
from icos.kernel.events.types import Event

from icos.game.rules.dice import Dice
from icos.game.runtime.actor import AttackProfile, Combatant


@dataclass
class RulesEngine:
    dice: Dice

    def roll_initiative(self, combatants: List[Combatant]) -> Tuple[List[str], List[Event]]:
        events: List[Event] = []
        rolls: List[Tuple[int, int, str, str]] = []

        for combatant in combatants:
            total = self.dice.d20() + combatant.dex_mod
            rolls.append((total, combatant.dex_mod, combatant.id, combatant.name))
            events.append(
                Event(
                    type="initiative",
                    actor=combatant.id,
                    message=f"{combatant.name} rolls initiative: d20+{combatant.dex_mod} = {total}",
                    data={"total": total, "dex_mod": combatant.dex_mod},
                )
            )

        rolls.sort(key=lambda x: (x[0], x[1], x[3]), reverse=True)
        order = [cid for _, _, cid, _ in rolls]
        return order, events

    def resolve_action(self, state: EncounterState[Combatant], action: ActionRequest) -> List[Event]:
        match action.action_id:
            case "attack":
                return self._resolve_attack(state, action)
            case "defend":
                return self._resolve_defend(state, action)
            case "heal":
                return self._resolve_heal(state, action)
            case "wait":
                return self._resolve_wait(state, action)
            case _:
                raise ValueError(f"Unsupported action_id: {action.action_id!r}")

    def _resolve_defend(self, state: EncounterState[Combatant], action: ActionRequest) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []

        actor.flags.add("defending")
        return [
            Event(
                type="defend",
                actor=actor.id,
                message=(
                    f"{actor.name} takes a defensive stance "
                    "(attacks against them have disadvantage until their next turn)."
                ),
                data={"flag_added": "defending"},
            )
        ]

    def _resolve_heal(self, state: EncounterState[Combatant], action: ActionRequest) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []

        if actor.heals_remaining <= 0:
            return [
                Event(
                    type="heal_failed",
                    actor=actor.id,
                    message=f"{actor.name} tries to heal but has no heals remaining.",
                    data={"heals_remaining": actor.heals_remaining},
                )
            ]

        heal_dice = str(action.data.get("heal_dice", actor.heal_dice))
        roll = self.dice.roll(heal_dice)
        heal_bonus = actor.equipment_heal_bonus

        before = actor.hp
        actor.set_hp(actor.hp + roll.total + heal_bonus)
        healed = actor.hp - before
        actor.heals_remaining -= 1

        return [
            Event(
                type="heal",
                actor=actor.id,
                message=(
                    f"{actor.name} heals for {healed} (rolled {heal_dice} => {roll.total}). "
                    f"HP {before} -> {actor.hp} | heals left: {actor.heals_remaining}"
                ),
                data={
                    "heal": healed,
                    "hp_before": before,
                    "hp_after": actor.hp,
                    "heal_dice": heal_dice,
                    "heal_bonus": heal_bonus,
                    "heals_remaining": actor.heals_remaining,
                },
            )
        ]

    def _resolve_wait(self, state: EncounterState[Combatant], action: ActionRequest) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []
        return [Event(type="wait", actor=actor.id, message=f"{actor.name} waits.")]

    def _resolve_attack(self, state: EncounterState[Combatant], action: ActionRequest) -> List[Event]:
        events: List[Event] = []

        attacker = state.get(action.actor_id)
        if not attacker.alive or not action.targets:
            return events

        defender = state.get(action.targets[0])
        if not defender.alive:
            return events

        attack_index = int(action.data.get("attack_index", 0))
        attack: AttackProfile = attacker.choose_attack(attack_index)

        adv_state = self._adv_state(attacker, defender, attack)
        d20, underlying = self.dice.d20_with_adv_state(adv_state)
        total_attack_bonus = attack.attack_bonus + attacker.equipment_attack_bonus
        total_to_hit = d20 + total_attack_bonus
        defender_ac = defender.effective_ac

        rolls_str = ", ".join(map(str, underlying))
        message = (
            f"{attacker.name} uses {attack.name}: d20({rolls_str}) -> {d20} + {total_attack_bonus} = "
            f"{total_to_hit} vs AC {defender_ac}"
        )
        if adv_state == "adv":
            message += " (ADVANTAGE)"
        if adv_state == "dis":
            message += " (DISADVANTAGE)"

        events.append(
            Event(
                type="attack_roll",
                actor=attacker.id,
                target=defender.id,
                message=message,
                data={
                    "underlying_d20": underlying,
                    "chosen_d20": d20,
                    "attack_bonus": total_attack_bonus,
                    "total": total_to_hit,
                    "target_ac": defender_ac,
                    "adv_state": adv_state,
                },
            )
        )

        is_crit = d20 == 20
        hit = is_crit or total_to_hit >= defender_ac
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

        damage_total, detail = self._roll_damage(attack.damage_dice, is_crit)
        damage_total = max(0, damage_total + attacker.equipment_damage_bonus)

        before = defender.hp
        defender.set_hp(defender.hp - damage_total)

        events.append(
            Event(
                type="damage",
                actor=attacker.id,
                target=defender.id,
                message=(
                    f"{defender.name} takes {damage_total} {attack.damage_type} damage ({detail}). "
                    f"HP {before} -> {defender.hp}"
                ),
                data={
                    "amount": damage_total,
                    "damage_type": attack.damage_type,
                    "attacker_damage_bonus": attacker.equipment_damage_bonus,
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

    @staticmethod
    def _adv_state(attacker: Combatant, defender: Combatant, attack: AttackProfile) -> str:
        adv = 0
        dis = 0

        if "defending" in defender.flags:
            dis += 1

        for c in ("poisoned", "blinded", "restrained"):
            if attacker.has_condition(c):
                dis += 1

        for c in ("blinded", "restrained", "stunned", "paralyzed", "unconscious"):
            if defender.has_condition(c):
                adv += 1

        if defender.has_condition("prone"):
            if attack.attack_kind == "ranged":
                dis += 1
            else:
                adv += 1

        if adv > 0 and dis == 0:
            return "adv"
        if dis > 0 and adv == 0:
            return "dis"
        return "normal"

    def _roll_damage(self, dice_notation: str, is_crit: bool) -> Tuple[int, str]:
        if is_crit:
            dmg1 = self.dice.roll(dice_notation)
            dmg2 = self.dice.roll(dice_notation)
            total = dmg1.total + dmg2.total
            return total, f"{dice_notation} crit => {dmg1.total} + {dmg2.total} = {total}"

        dmg = self.dice.roll(dice_notation)
        return dmg.total, f"{dice_notation} => {dmg.total}"
