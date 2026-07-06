# BUGLIST_CONNECTORS_SAVE — Save trust + connector routing audit (Milestone 3E)

Audit of the save pipeline and connector tooling that led to lost work after a
refresh even though the UI showed "saved".

## Files inspected

- `frontend/src/App.tsx`
- `frontend/src/components/CanvasEditor.tsx`
- `frontend/src/components/connector.ts`
- `frontend/src/components/Ribbon.tsx`
- `frontend/src/components/PropertiesPanel.tsx`
- `frontend/src/components/DocumentView.tsx` / `PageRenderer.tsx` / `NormalizedPage.tsx`
- `frontend/src/api/client.ts`
- `core/project_store.py`
- `server.py`
- `scripts/smoke_editor_browser.py`

## Canvas → project → server data flow

```text
CanvasEditor (Fabric) --onSerializedChange--> NormalizedPage --> PageRenderer
   --> DocumentView --> App.onCanvasChange(pageId, objects) --> setProject(...)
   --> autosave useEffect([project]) --> saveProject(project) POST /api/projects/<id>
```

## Findings

### Why "SAVED" can show without persisted canvas state

- **Stale pill during the debounce window.** The autosave effect debounces 600ms
  (`setTimeout`). The `saveStatus` pill still reads `saved` from the PRIOR save
  while a new edit sits un-persisted in the debounce. A refresh inside that window
  loses the newest edit while the pill still says "saved". **(root cause)**
- **No dirty state.** There was no distinct `Unsaved Changes` state; the pill only
  toggled `saving`/`saved`/`failed`, so a pending edit looked identical to a
  persisted one.
- **Two independent save paths.** `saveProject()` (autosave) and `savePages()`
  (structural page ops) both write, but only the autosave path updated the pill.
  A `savePages()` failure never surfaced as `Save Failed`.

### Where canvasObjects are saved

- Per page in `project.pages[i].canvasObjects` (serialized Fabric objects).
- Written whole-project by `ProjectStore.save()` to
  `.docs/projects/<slug>__<id>/project.json`.

### Autosave cadence / debounce / throttle

- Debounced 600ms via `setTimeout` in a `useEffect([project, printMode])`.
- Awaited, but the awaited object is a closure over `project`; a newer edit during
  the in-flight save was not re-saved deterministically (no "save again if changed
  during save" guard).

### Whether canvas changes mark the project dirty

- Indirectly: `onCanvasChange` calls `setProject`, which re-triggers autosave. But
  there was **no explicit dirty flag** and no user-visible "Unsaved Changes".

### Whether save promises are awaited

- Autosave: yes. `savePages` (page ops): fire-and-forget (`void savePages(...)`),
  so structural changes could fail silently.

### Flush before page switch / export / open / upload / unload

- **Missing.** No `beforeunload` guard and no flush before switching pages,
  exporting, opening another project, or uploading. A mid-edit navigation could
  drop the last serialization.

### How connector objects serialize

- `connector.ts` `toObject()` writes `pointsData` (absolute route) as the single
  source of truth plus `arrowStart/arrowEnd/connectorKind/label/objName`.
- `fromObject()` rebuilds from `pointsData`. This part is **sound** — routes and
  arrows round-trip. Missing: `stylePreset`, `wireNumber`, `labelStart/Middle/End`,
  `locked`, `layer` (added in this milestone for forward-compat).

### Undo/redo of connector changes

- Yes — history snapshots the whole canvas via `toObject(SER_PROPS)`, which
  includes connectors and their `pointsData`.

### Whether line duplicates are supported

- `duplicateSelected()` clones the active object (+20px). It worked but offset was
  large; there was no Alt-drag duplicate and no dedicated connector copy affordance.

### Where page switching can lose active canvas changes

- Switching `activePageId` unmounts `CanvasEditor`. Fabric events persist edits
  synchronously, so committed edits survive, but a **mid-gesture** edit or a
  pending debounced save could be lost on fast navigation. Flushing before switch
  removes this risk.

## Fixes shipped in Milestone 3E

- Trustworthy save states: `Unsaved Changes → Saving… → Saved HH:MM:SS / Save Failed`,
  driven by a single centralized save manager with a "save again if changed during
  save" guard and an awaited `flushSave()`.
- Flush + guard before page switch, export, open, upload, and `beforeunload`.
- Local recovery snapshots to `localStorage` (last 10 per project) after canvas edits.
- Server-side backups: prior `project.json` copied to
  `.docs/projects/<id>/backups/project_<ts>.json` before overwrite (keep 20), with
  list + restore endpoints and a Backups / Recovery modal.
- Connector object model extended (`stylePreset`, `wireNumber`, `labelStart/Middle/End`,
  `locked`, `layer`) with `pointsData` remaining the single route source of truth.
- Easier connectors: larger hit band, Alt-drag duplicate, 12px duplicate offset,
  `L/P/E/B` tool shortcuts, drawing hint in the status bar.
- Minimal Bus/Harness tool: N parallel connectors between two points with a shared
  style preset and per-wire labels.

## Honest remaining (not fully done this pass)

- Full component **ports/pin terminal rows** with binding that reflows on component
  move (Phase E) — only endpoint-to-object snapping groundwork is in place.
- Trunk + branch bus routing with automatic fan-out (Phase F "better") — the minimal
  parallel-wire bus is implemented instead.
- Per-region (start/middle/end) inline label editing by double-click position
  (Phase H) — labels are editable via the properties panel and a single mid label.
