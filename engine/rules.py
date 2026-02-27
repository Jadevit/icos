# engine/rules.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .dice import Dice
from .models import AttackProfile, Combatant, Event
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

    def resolve_basic_attack(
        self,
        state: CombatState,
        attacker: Combatant,
        defender: Combatant,
    ) -> List[Event]:
        events: List[Event] = []

        atk: AttackProfile = attacker.choose_basic_attack()
        d20 = self.dice.d20()
        total_to_hit = d20 + atk.attack_bonus

        attack_msg = (
            f"{attacker.name} uses {atk.name}: " f"d20({d20}) + {atk.attack_bonus} = {total_to_hit} vs AC {defender.ac}"
        )
        events.append(
            Event(
                type="attack_roll",
                actor=attacker.id,
                target=defender.id,
                message=attack_msg,
                data={
                    "d20": d20,
                    "attack_bonus": atk.attack_bonus,
                    "total": total_to_hit,
                    "target_ac": defender.ac,
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

        # Damage: if crit, double the dice portion by rolling twice.
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
