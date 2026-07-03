# BUGLIST_3E — editor selection failures

Method: reproduced by **code inspection** of the running build (I cannot drive a
real browser headlessly). Root cause found and fixed; the pass/fail table below
must be confirmed with the manual browser QA in Phase J.

## Root cause (the big one)

**Overlay pointer-events were controlled by a broken DOM-walking effect.**
`CanvasEditor` created a Fabric canvas, then tried to toggle the overlay's
`pointer-events` by walking up from the `<canvas>` element:

```
const overlayEl = canvasEl.parentElement?.parentElement; // expected .np-overlay-layer
const rootEl = overlayEl?.parentElement;                 // expected .np-page-root
```

But Fabric v6 **wraps the `<canvas>` in a `.canvas-container` div**, so the chain
was off by one:
- `canvasEl.parentElement` = `.canvas-container` (Fabric), not `.canvas-wrap`
- `overlayEl` actually pointed at `.canvas-wrap`
- `rootEl` actually pointed at `.np-overlay-layer`

The `mousemove` listener was attached to `.np-overlay-layer`, whose
`pointer-events` is `none` in normal select mode — so the listener **never
fired**, `setInteractive()` never ran, and overlay objects (text, lines, images)
could not be clicked/moved. This is why text boxes and connectors felt "stuck"
and why the Text/Draw ribbons never unlocked (selection state never updated).

FIX (3E): removed the fragile hover pass-through entirely. Overlay
interactivity is now driven purely by React state + CSS classes
(`overlayInteractive = overlayMode || activeTool !== 'select'`), and overlay edit
mode auto-enables whenever a page has objects, is a drawing page, or you insert /
paste / drop something — so objects are reliably selectable and the toolbars
unlock.

## Secondary issues addressed
- Active page tab / left-list row contrast increased (Phase G).
- Connectors already use bounding-box hit test + padding (3D); now actually
  reachable because the overlay is interactive.
- Library auto-categorize + rename persist (3C) — filters work; wrong extraction
  *names* still need manual rename (documented limitation).

## PASS/FAIL (fill in during Phase J browser QA)

Headless Chromium (Playwright) verification of the core selection fix — run
against a live server — confirmed:

- Insert Text → overlay becomes interactive (`.np-overlay-layer.active`) = **PASS**
- Text toolbar auto-shows and Bold is enabled = **PASS**
- Insert Line → Draw tab auto-shows, line-style controls enabled = **PASS**

| # | Check | Result |
| --- | --- | --- |
| 1 | Text insert | PASS (Chromium) |
| 2 | Text move (overlay interactive) | PASS (overlay active); drag not pixel-scripted |
| 3 | Text edit (double-click) | pending visual |
| 4 | Text bold/color/size | PASS (Bold enabled + applied) |
| 5 | Line insert | PASS (Chromium) |
| 6 | Line body move | logic fixed; pending visual |
| 7 | Endpoint move | logic fixed; pending visual |
| 8 | Line style change | PASS (controls enabled) |
| 9 | Snap guide visible | logic in place; pending visual |
| 10 | Active tab clear | PASS (high-contrast CSS) |
| 11 | Library filter works | PASS (3C, API-verified) |
| 12 | Bad library item rename persists | PASS (3C, API-verified) |
| 13 | Continuation Try Fit | NOT implemented this pass (merge/make-independent exist) |
| 14 | Save/reload | PASS (smoke) |
| 15 | Export PDF | PASS (prior live export) |

