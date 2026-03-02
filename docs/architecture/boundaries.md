# Boundaries

- `kernel` MUST NOT import from `game`, `content`, or `adapters`.
- `game` MAY import from `kernel` and `content`.
- `adapters` SHOULD call `app/services` instead of mutating game state directly.
- Content models are immutable definitions; runtime instances are mutable simulation state.
