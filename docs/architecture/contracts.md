# Contracts

Stable contracts are defined by:

- Action request shape (`icos.tact.core.actions.ActionRequest`)
- Event shape (`icos.tact.events.types.Event`)
- Encounter state progression (`icos.tact.core.state.EncounterState`)

`core/` models live mutable runtime state.
`contracts/` models versioned serialized records for replay/interchange.

Future Rust porting should preserve these contracts first, then port rules/systems.
