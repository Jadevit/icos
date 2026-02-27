# engine/dice.py
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union


Number = Union[int, float]


@dataclass(frozen=True)
class RollResult:
    """
    Standard roll result you can log/serialize later.
    - total: final value after modifiers
    - rolls: individual die results (empty for constant-only expressions)
    - modifier: flat modifier applied after summing dice
    - notation: the original dice expression, if any (e.g. "2d6+3")
    """

    total: int
    rolls: List[int]
    modifier: int = 0
    notation: str = ""


@dataclass(frozen=True)
class DiceExpr:
    """
    Parsed dice expression like: 2d6+3, d20, 4d8-2
    """

    num_dice: int
    sides: int
    modifier: int = 0

    def __post_init__(self) -> None:
        if self.num_dice < 0:
            raise ValueError("num_dice must be >= 0")
        if self.num_dice > 0 and self.sides <= 0:
            raise ValueError("sides must be > 0 when num_dice > 0")


# Matches:
#  - "d20"
#  - "2d6"
#  - "2d6+3"
#  - "2d6-1"
# Allows whitespace.
_DICE_RE = re.compile(r"^\s*(?:(\d*)d(\d+))\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


def parse_dice(notation: str) -> DiceExpr:
    """
    Parse standard dice notation: NdM±K
      - "d20" => 1d20
      - "2d6+3" => 2d6 + 3
      - "0d6+5" is allowed (constant-only roll via modifier with 0 dice)

    Raises ValueError for invalid notation.
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
    Dice roller wrapper so you can:
    - seed for reproducible tests
    - swap RNG later if needed
    """

    def __init__(self, seed: Optional[int] = None, rng: Optional[random.Random] = None) -> None:
        self._rng = rng if rng is not None else random.Random(seed)

    # --- Core primitives ---

    def roll_die(self, sides: int) -> int:
        """Roll 1..sides."""
        if sides <= 0:
            raise ValueError("sides must be > 0")
        return self._rng.randint(1, sides)

    def roll_dice(self, num_dice: int, sides: int) -> RollResult:
        """
        Roll N dice with S sides. Returns total and individual rolls.
        """
        if num_dice < 0:
            raise ValueError("num_dice must be >= 0")
        if num_dice > 0 and sides <= 0:
            raise ValueError("sides must be > 0 when num_dice > 0")

        rolls = [self.roll_die(sides) for _ in range(num_dice)]
        return RollResult(total=sum(rolls), rolls=rolls, modifier=0, notation=f"{num_dice}d{sides}")

    # --- Common helpers ---

    def d20(self) -> int:
        return self.roll_die(20)

    def d12(self) -> int:
        return self.roll_die(12)

    def d10(self) -> int:
        return self.roll_die(10)

    def d8(self) -> int:
        return self.roll_die(8)

    def d6(self) -> int:
        return self.roll_die(6)

    def d4(self) -> int:
        return self.roll_die(4)

    # --- 5e-ish helpers (advantage / disadvantage) ---

    def d20_advantage(self) -> Tuple[int, Tuple[int, int]]:
        """
        Roll 2d20, take the higher.
        Returns: (chosen, (a, b))
        """
        a = self.d20()
        b = self.d20()
        return (a if a >= b else b), (a, b)

    def d20_disadvantage(self) -> Tuple[int, Tuple[int, int]]:
        """
        Roll 2d20, take the lower.
        Returns: (chosen, (a, b))
        """
        a = self.d20()
        b = self.d20()
        return (a if a <= b else b), (a, b)

    def d20_with_adv_state(self, adv_state: str = "normal") -> Tuple[int, Tuple[int, ...]]:
        """
        adv_state: "normal" | "adv" | "dis"
        Returns: (chosen_roll, underlying_rolls)
        """
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

    # --- Notation rolls ---

    def roll(self, notation: str) -> RollResult:
        """
        Roll dice from notation like "2d6+3" or "d20-1".
        Returns RollResult(total, rolls, modifier, notation).
        """
        expr = parse_dice(notation)
        rolls: List[int] = []
        if expr.num_dice > 0:
            rolls = [self.roll_die(expr.sides) for _ in range(expr.num_dice)]
        total = sum(rolls) + expr.modifier
        return RollResult(total=total, rolls=rolls, modifier=expr.modifier, notation=notation.strip())

    def roll_expr(self, expr: DiceExpr, notation: str = "") -> RollResult:
        """
        Roll from a pre-parsed DiceExpr (avoids reparsing).
        """
        rolls: List[int] = []
        if expr.num_dice > 0:
            rolls = [self.roll_die(expr.sides) for _ in range(expr.num_dice)]
        total = sum(rolls) + expr.modifier
        return RollResult(total=total, rolls=rolls, modifier=expr.modifier, notation=notation)

    # --- Utility ---

    @staticmethod
    def format_roll(result: RollResult) -> str:
        """
        Friendly string for logs.
        Examples:
          - "2d6+3 => [4, 2] +3 = 9"
          - "d20 => [17] = 17"
          - "0d6+5 => [] +5 = 5"
        """
        rolls_part = f"{result.rolls}"
        mod = result.modifier
        if mod == 0:
            return f"{result.notation} => {rolls_part} = {result.total}".strip()
        sign = "+" if mod > 0 else "-"
        return f"{result.notation} => {rolls_part} {sign}{abs(mod)} = {result.total}".strip()


# Convenience singleton if you don’t want to instantiate Dice everywhere yet.
DEFAULT_DICE = Dice()


# --- Minimal functional API (if you prefer functions over objects right now) ---


def roll_die(sides: int) -> int:
    return DEFAULT_DICE.roll_die(sides)


def roll_dice(num_dice: int, sides: int) -> RollResult:
    return DEFAULT_DICE.roll_dice(num_dice, sides)


def roll(notation: str) -> RollResult:
    return DEFAULT_DICE.roll(notation)


def d20() -> int:
    return DEFAULT_DICE.d20()
