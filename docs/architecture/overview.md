# Icos Architecture Overview

Icos is split into four top-level layers:

- `icos.tact`: deterministic turn simulation kernel.
- `icos.game`: gameplay logic and rules built atop tact.
- `icos.content`: content compilation/loading and typed entity models.
- `icos.adapters`: user/system interfaces (CLI, future UI/LLM/networking).

Tact is kept extractable by ensuring it has no dependencies on game/content/adapters.
