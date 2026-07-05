# Singh360_SmartDraw — Project Board (canonical)

Milestone **4A — Professional EMS Drawing Standard + Clean Component Library V2**.
Update statuses here as work progresses. `In Progress` = actively being built,
`Done` = implemented + smoke-tested, `Backlog` = not started.

## Milestone 4A

| Phase | Item | Status |
| ----- | ---- | ------ |
| 0 | Clean library root `.docs/library/components` + manifest/aliases/connector scaffolding | Done |
| 1 | Component manifest v2 schema (ports, symbolFile, labels) + immediate persistence | Done |
| 2 | Simplified library UI (search / category / All-Favorites-Needs Review / grid-list / add / refresh / rebuild / clean) | Done |
| 3 | Black-and-white SVG symbol generation per category | Done |
| 4 | Drawing style standard + line/connector presets (B&W readable) | Done |
| 5 | Professional page templates (overall layout, one-line, device plan, PDF underlay, schedule) | Done |
| 6 | Crisp PDF import (PyMuPDF, auto-crop, 400–600 DPI, locked underlay) | Done |
| 7 | Data-driven generators (overall layout, component rack/stack, callout schedule) | Done |
| 8 | EMS sheet numbering scheme (EMS 0.0 … 9.x) | Done |
| 9 | Tests + git hygiene | Done |

## Honest flags (carry forward)

- VSDX / Visio visual fidelity is proven only at package level — confirm in a Visio client.
- SmartDraw VSON wire field names remain an integration contract to confirm.
- PDF underlay visual crispness must be eyeballed at 100% + exported 17×11.
- RDM XML dialect must be confirmed against a native Layout Editor sample.
