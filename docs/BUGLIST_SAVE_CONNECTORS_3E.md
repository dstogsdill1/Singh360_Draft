# BUGLIST_SAVE_CONNECTORS_3E — Save data-loss + connector UX audit

## 1. How canvas objects are stored per page

Every `PageModel` has a `canvasObjects: Record<string, unknown>[]` field that holds
the serialised Fabric object tree for that page. It is persisted inside
`project.json` on the server at
`.docs/projects/<slug>__<id>/project.json`.

## 2. What triggers a save

A `useEffect([project, ...])` debounce in `App.tsx` fires 800 ms after any
`setProject(...)` call and POSTs the whole project via `saveProject()`.

## 3. Whether the active Fabric canvas is serialised before critical actions

| Action | Serialised before? |
| --- | --- |
| `Save Now` / Ctrl+S | **No — root cause bug.** Reads stale `projectRef.current`. |
| Page switch (SheetManager) | **No.** Calls `void flushSave()` on the stale ref, then switches. |
| Tab switch (DocumentView) | **No.** |
| Export PDF | **No.** `flushSave()` on stale ref. |
| Browser refresh | 800 ms debounce may not have fired. |
| `beforeunload` | Only warns if status is unsaved; does not flush. |

## 4. Root cause of "SAVED" showing without persistence

The data flow is:

```text
Fabric event → persist() → onSerRef.current(data)
  → onCanvasChange(pageId, objects) → setProject(next)   [React async]
  → useEffect([project]) debounce → flushSave()
```

`setProject` is a React async state update. Until React commits the update and
re-renders, `projectRef.current` still holds the **old project** (without the new
canvas objects). When the user clicks **Save Now** or **switches pages** before the
React commit cycle completes, `flushSave()` reads the stale ref and saves an older
snapshot. The server returns 200, the UI shows **Saved**, and the new objects are
lost.

## 5. Connector serialisation issues (before this fix)

- `pointsData` (absolute coordinates) is stored alongside the legacy Fabric
  `points[]` array (local coordinates). On reload, `fromObject` uses `pointsData`
  when present, which is correct.
- `SER_PROPS` now includes all Phase-B extended fields.
- Ghost lines and stuck draw modes occurred because `finalizeRef` could be called
  before the Fabric canvas was ready. Fixed by moving finalize into the mount
  effect closure.

## 6. Why duplicate/move/endpoint editing was unreliable

- Connectors are Fabric `Polyline` subclasses. `applyVertexControls()` calls
  `createPolyControls()` which creates one handle per `this.points[]` entry. If
  `pointsData` was not normalised to `points[]` correctly on deserialise, the
  control handles appeared in wrong positions.
- Duplicate used a 20 px offset, making duplicates nearly invisible on top of
  originals (fixed to 12 px).

## 7. Fixes shipped in this pass

- Add `captureCanvas(): Record<string, unknown>[]` to `CanvasApi`. This
  **synchronously** reads the live Fabric canvas and returns the serialised
  object list — bypassing the React async state update pipeline entirely.
- Add `captureActivePage()` to `App.tsx`. It reads the Fabric canvas via
  `canvasApiRef.current.captureCanvas()`, immediately writes the result into
  **both** `projectRef.current` and React state, and calls `flushSave()` with
  the guaranteed-fresh project.
- All page-switch paths (`SheetManager.onSelect`, `DocumentView.onSelectPage`,
  `buildPageActions`), `saveNow`, `flushSave`, export PDF/package, and open-project
  now call `captureActivePage()` first.
- Ctrl+S keyboard shortcut calls `captureActivePage()` + `saveNow`.
- Port snap: When a connector draw tool (`line`, `arrow`, `polyline`, `elbow`) is
  active, hovering over any image/component/shape shows 9 snap dots at the
  canonical anchor points (8 edges/corners + centre). Moving a connector endpoint
  within 18 px of a snap dot snaps it there.
