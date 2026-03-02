from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

Number = Union[int, float]


@dataclass(frozen=True)
class RollResult:
    """
    Standard roll result suitable for logging and serialization.
    """
    total: int
    rolls: List[int]
    modifier: int = 0
    notation: str = ""


@dataclass(frozen=True)
class DiceExpr:
    """
    Parsed dice expression: NdM±K (example: 2d6+3, d20, 4d8-2).
    """
    num_dice: int
    sides: int
    modifier: int = 0

    def __post_init__(self) -> None:
        if self.num_dice < 0:
            raise ValueError("num_dice must be >= 0")
        if self.num_dice > 0 and self.sides <= 0:
            raise ValueError("sides must be > 0 when num_dice > 0")


_DICE_RE = re.compile(r"^\s*(?:(\d*)d(\d+))\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


def parse_dice(notation: str) -> DiceExpr:
    """
    Parse standard dice notation: NdM±K
      - "d20" => 1d20
      - "2d6+3" => 2d6 + 3
      - "0d6+5" => constant-only roll via modifier with 0 dice
    """
    m = _DICE_RE.match(notation)
    if not m:
        raise ValueError(f"Invalid dice notation: {notation!r}")

    n_str, sides_str, mod_str = m.groups()
    num_dice = 1 if (n_str is None or n_str.strip() == "") else int(n_str)
    sides = int(sides_str)

    modifier = 0
    if mod_str:
        modifier = int(mod_str.replace(" ", ""))

    return DiceExpr(num_dice=num_dice, sides=sides, modifier=modifier)


class Dice:
    """
    Dice roller wrapper for reproducible tests and deterministic simulation.
    """

    def __init__(self, seed: Optional[int] = None, rng: Optional[random.Random] = None) -> None:
        self._rng = rng if rng is not None else random.Random(seed)

    def roll_die(self, sides: int) -> int:
        if sides <= 0:
            raise ValueError("sides must be > 0")
        return self._rng.randint(1, sides)

    def roll_dice(self, num_dice: int, sides: int) -> RollResult:
        if num_dice < 0:
            raise ValueError("num_dice must be >= 0")
        if num_dice > 0 and sides <= 0:
            raise ValueError("sides must be > 0 when num_dice > 0")

        rolls = [self.roll_die(sides) for _ in range(num_dice)]
        return RollResult(total=sum(rolls), rolls=rolls, modifier=0, notation=f"{num_dice}d{sides}")

    def d20(self) -> int:
        return self.roll_die(20)

    def d20_advantage(self) -> Tuple[int, Tuple[int, int]]:
        a = self.d20()
        b = self.d20()
        return (a if a >= b else b), (a, b)

    def d20_disadvantage(self) -> Tuple[int, Tuple[int, int]]:
        a = self.d20()
        b = self.d20()
        return (a if a <= b else b), (a, b)

    def d20_with_adv_state(self, adv_state: str = "normal") -> Tuple[int, Tuple[int, ...]]:
        adv_state = adv_state.lower().strip()
        if adv_state in ("normal", "n", ""):
            r = self.d20()
            return r, (r,)
        if adv_state in ("adv", "a", "advantage"):
            chosen, pair = self.d20_advantage()
            return chosen, pair
        if adv_state in ("dis", "d", "disadvantage"):
            chosen, pair = self.d20_disadvantage()
            return chosen, pair
        raise ValueError("adv_state must be 'normal', 'adv', or 'dis'")

    def roll(self, notation: str) -> RollResult:
        expr = parse_dice(notation)
        rolls: List[int] = []
        if expr.num_dice > 0:
            rolls = [self.roll_die(expr.sides) for _ in range(expr.num_dice)]
        total = sum(rolls) + expr.modifier
        return RollResult(total=total, rolls=rolls, modifier=expr.modifier, notation=notation.strip())

    def roll_expr(self, expr: DiceExpr, notation: str = "") -> RollResult:
        rolls: List[int] = []
        if expr.num_dice > 0:
            rolls = [self.roll_die(expr.sides) for _ in range(expr.num_dice)]
        total = sum(rolls) + expr.modifier
        return RollResult(total=total, rolls=rolls, modifier=expr.modifier, notation=notation)

    @staticmethod
    def format_roll(result: RollResult) -> str:
        rolls_part = f"{result.rolls}"
        mod = result.modifier
        if mod == 0:
            return f"{result.notation} => {rolls_part} = {result.total}".strip()
        sign = "+" if mod > 0 else "-"
        return f"{result.notation} => {rolls_part} {sign}{abs(mod)} = {result.total}".strip()