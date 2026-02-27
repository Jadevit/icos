# engine/systems/combat/resolution.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from ...dice import Dice
from ...models import ActionDeclaration, AttackProfile, Combatant, Event
from ...state import CombatState


@dataclass
class RulesEngine:
    """
    Combat resolution (mechanics authority).

    Controllers declare actions. This resolver turns them into:
      - factual Events
      - deterministic state mutation

    Lives under systems/combat because it is gameplay logic ("verbs").
    """
    dice: Dice

    # --- Initiative -------------------------------------------------

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

        # High to low; tie-break by dex_mod then name for stability
        rolls.sort(key=lambda x: (x[0], x[1], x[3]), reverse=True)
        order = [cid for _, _, cid, _ in rolls]
        return order, events

    # --- Action resolution -----------------------------------------

    def resolve_action(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        match action.type:
            case "attack":
                return self._resolve_attack(state, action)
            case "defend":
                return self._resolve_defend(state, action)
            case "heal":
                return self._resolve_heal(state, action)
            case "wait":
                return self._resolve_wait(state, action)
            case _:
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
                message=(
                    f"{actor.name} takes a defensive stance "
                    "(attacks against them have disadvantage until their next turn)."
                ),
                data={"flag_added": "defending"},
            )
        ]

    def _resolve_heal(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []

        if actor.heals_remaining <= 0:
            return [
                Event(
                    type="turn_start",
                    actor=actor.id,
                    message=f"{actor.name} tries to heal but has no heals remaining.",
                    data={"heals_remaining": actor.heals_remaining},
                )
            ]

        heal_dice = str(action.data.get("heal_dice", actor.heal_dice))
        roll = self.dice.roll(heal_dice)

        before = actor.hp
        actor.hp = min(actor.max_hp, actor.hp + roll.total)
        healed = actor.hp - before
        actor.heals_remaining -= 1

        return [
            Event(
                type="damage",  # keeping event types minimal for now
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
                    "heals_remaining": actor.heals_remaining,
                },
            )
        ]

    def _resolve_wait(self, state: CombatState, action: ActionDeclaration) -> List[Event]:
        actor = state.get(action.actor_id)
        if not actor.alive:
            return []
        return [Event(type="turn_start", actor=actor.id, message=f"{actor.name} waits.")]

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

        rolls_str = ", ".join(map(str, underlying))
        attack_msg = (
            f"{attacker.name} uses {atk.name}: d20({rolls_str}) -> {d20} + {atk.attack_bonus} = {total_to_hit} "
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

        dmg_total, detail = self._roll_damage(atk.damage_dice, is_crit)

        before = defender.hp
        defender.hp = max(0, defender.hp - dmg_total)

        events.append(
            Event(
                type="damage",
                actor=attacker.id,
                target=defender.id,
                message=(
                    f"{defender.name} takes {dmg_total} {atk.damage_type} damage ({detail}). "
                    f"HP {before} -> {defender.hp}"
                ),
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

    def _roll_damage(self, dice_notation: str, is_crit: bool) -> Tuple[int, str]:
        if is_crit:
            dmg1 = self.dice.roll(dice_notation)
            dmg2 = self.dice.roll(dice_notation)
            total = dmg1.total + dmg2.total
            detail = f"{dice_notation} crit => {dmg1.total} + {dmg2.total} = {total}"
            return total, detail

        dmg = self.dice.roll(dice_notation)
        return dmg.total, f"{dice_notation} => {dmg.total}"