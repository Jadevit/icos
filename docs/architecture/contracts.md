# Contracts

Stable contracts are defined by:

- Action request shape (`icos.kernel.core.actions.ActionRequest`)
- Event shape (`icos.kernel.events.types.Event`)
- Encounter state progression (`icos.kernel.core.state.EncounterState`)

Future Rust porting should preserve these contracts first, then port rules/systems.
