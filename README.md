# Icos

Icos is a self-contained fantasy tabletop RPG engine project.

It’s currently built on a 5e-style rules foundation for speed and structure, but the long-term goal is to evolve into its own system over time. The engine is designed to run entirely from local data (no live API dependency).

## Status

**Current checkpoint:** a working CLI combat loop with deterministic engine resolution.

- Loads monsters from local `data/ref.db` (SQLite)
- Runs turn-based combat with initiative, HP, attacks, and basic actions
- Player chooses actions via CLI
- Enemy uses simple non-LLM combat policy
- Engine emits factual events as the source of truth

## Run

```bash
python run.py
# or deterministic:
python run.py --seed 42
```
