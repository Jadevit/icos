# Icos

Icos is a modular tabletop-inspired roguelike prototype.

## Structure

- `src/icos/kernel/`: deterministic encounter kernel (turn state, actions, events, session loop)
- `src/icos/game/`: Icos gameplay systems (combat, runtime actors/inventory, rules)
- `src/icos/content/`: content pipeline, typed definitions, codex DB access/store
- `src/icos/adapters/cli/`: interactive CLI adapter and command surface
- `src/icos/app/services/`: game-facing orchestration service (`GameEngine`)
- `docs/architecture/`: architecture boundaries/contracts/roadmap
- `data/`: packs, bundles, compiled codex DB artifacts

## Run

```bash
python3 run.py
# deterministic seed
python3 run.py --seed 42
# skip codex rebuild (dev)
python3 run.py --no-build
```

## Architecture Rules

- `kernel` does not depend on `game`, `content`, or adapters.
- `game` depends on `kernel` and `content`.
- adapters invoke services; they do not mutate state directly.
- runtime actor state is separate from content definitions.
