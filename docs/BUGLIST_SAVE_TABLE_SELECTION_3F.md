# BUGLIST — Emergency 3F Save, Tables, Selection

Date: 2026-07-06

## 1. How `canvasObjects` are stored per page

- Frontend page model: `frontend/src/model/types.ts` defines `PageModel.canvasObjects: Record<string, unknown>[]`.
- Render path: `NormalizedPage` passes `page.canvasObjects` into `CanvasEditor` as `serialized`.
- Edit path: `CanvasEditor` serializes Fabric objects with `canvas.toObject(SER_PROPS).objects` and reports them through `onSerializedChange`.
- App path: `DocumentView`/`NormalizedPage` call `onCanvasChange(page.id, objects)`, and `App.tsx` merges those objects into `project.pages[].canvasObjects`.
- Save path: `App.tsx` currently has `captureActivePage()` which reads the live Fabric canvas through `canvasApiRef.current.captureCanvas()` and writes the result into `projectRef.current.pages[].canvasObjects` before save/navigation.

## 2. How table/schedule blocks are stored per page

- Normalized output pages store tables inside `PageModel.blocks`.
- A table block is `PageBlock` with `type: 'table'`, optional `headers: string[]`, and `rows: string[][]`.
- Matrix-like pages use the same storage shape with `type: 'matrix'` and renderer variant differences.
- `TablePageRenderer` mutates only block-level `headers` and `rows` through `onChange`, which flows to `App.onBlockChange()` and updates `project.pages[].blocks[].headers/rows`.

## 3. How imported Excel cells become normalized tables

- Workbook upload calls `server.py` `/api/projects/new`, which calls `core.workbook_importer.import_workbook()`.
- Worksheet import calls `/api/projects/<id>/import/workbook-sheet`, which uses workbook/sheet import code to append new normalized pages.
- Imported cells are not rendered as an image by the editor. They are converted into page blocks (`table`/`matrix` etc.) with `headers` and `rows`, plus raw worksheet grids in `ProjectModel.worksheets[].grid`.
- Empty Excel cells should remain blank strings in normalized rows, not `nan`.

## 4. Whether edits update project JSON, source workbook data, or only canvas overlay

- Table edits update normalized `project.pages[].blocks[].headers/rows` only.
- Canvas edits update `project.pages[].canvasObjects` only.
- Source workbook files under `.docs/projects/<project>/sources/workbook/` are import sources and are not rewritten by current table editing.
- Raw `worksheets[].grid` may be edited in Source View, but normalized table edits do not automatically write back to the original XLSX.
- Project JSON is therefore the editable source of truth after import; the workbook remains provenance/import source.

## 5. What triggers Save Now

- Ribbon `Save Now` calls `App.saveNow()`.
- Ctrl+S global keyboard handler also calls `saveNow()`.
- Current `saveNow()` captures Fabric overlay, posts the entire project to `/api/projects/<id>`, and marks Saved after the request succeeds.

## 6. What triggers autosave

- A `useEffect` in `App.tsx` watches `project` changes.
- When `JSON.stringify(project) !== lastSavedJsonRef.current`, it marks Unsaved, writes a local recovery snapshot, and after 800 ms calls `flushSave()`.
- `flushSave()` posts `projectRef.current` to the backend, but previously did not first capture in-progress table/cell editing state.

## 7. What happens before page switch

- Page selection calls `switchPageSafely(id)`.
- That calls `ensureSavedBeforeNavigation()` → `captureAndSave()` → `captureActivePage()` → `flushSave()`.
- Current capture only reads Fabric canvas objects. It does not force a contenteditable table cell to commit before switching.

## 8. What happens before export

- PDF and package export call `captureAndSave()` before calling backend export routes.
- Because current capture only covers Fabric overlay, export can miss a currently-focused table edit whose `blur` has not yet flushed into React state/project JSON.

## 9. Why page switching can lose work

- React state updates from Fabric/table changes are asynchronous.
- `captureActivePage()` fixed one stale-state path for Fabric overlays, but only for `canvasObjects`.
- Table cell editing depends on `blur`. Clicking a tab/menu can unmount/switch before the latest text is safely written to `projectRef.current` and saved.
- Some page operations (`mutatePages`, `updatePages`) use current React `project` values and can race an active-page live canvas/table edit unless the active page is captured first.
- There is no explicit guard against replacing a non-empty active page with empty overlay/table state from a stale closure.

## 10. Why imported tables are not editable

- They are technically contenteditable, but edit reliability is weak:
  - commit is mostly `onBlur` only;
  - Enter/Esc/Tab behavior is not controlled;
  - clipboard routing can be stolen by app-level paste if focus detection fails;
  - overlay interactivity can put the Fabric canvas above the base layer when `hasOverlay` is true, making table cells hard or impossible to click on annotated table pages.
- The UI does not track a selected table cell as first-class editor state, so Save/Properties/right-click cannot reliably know what cell is currently being edited.

## 11. Where right-click table actions are handled

- `frontend/src/components/renderers/TablePageRenderer.tsx` handles context menus for `<th>` and `<td>`.
- It currently exposes add row above/below, duplicate row, delete row, add/delete columns, and clear cell.
- It does not yet expose Copy Cell, Paste Cell, Duplicate Table, Resize Columns, or Fit Table to Body.
- It does not prevent all table menu operations from racing an active contenteditable value.

## 12. How object selection / multi-select currently works

- Fabric canvas selection is enabled in `CanvasEditor` when `activeTool === 'select'`.
- Single click and marquee selection are delegated to Fabric.
- `CanvasEditor` imports and uses Fabric `ActiveSelection`, and operations like align/distribute inspect `active.type === 'activeselection'`.
- Ctrl-click/Shift-click depends on Fabric defaults and is not explicitly configured/tested.
- Selection summary currently describes only the active object; multi-selection summary is limited.
- Thin connectors rely on `targetFindTolerance`/connector padding for hit testing.

## 13. How lock state is stored and enforced

- Lock state is stored as Fabric object flags: `lockMovementX`, `lockMovementY`, `lockScalingX`, `lockScalingY`, and `lockRotation`.
- `CanvasSelection.locked` is derived from `obj.lockMovementX === true`.
- `updateSelected({ locked })` sets movement/scale/rotation locks.
- Current delete/duplicate/group/z-order operations do not consistently block locked objects.
- `SER_PROPS` does not explicitly list all lock props, relying on Fabric serialization for built-in properties; this needs verification and explicit safety.

## 14. What must be fixed in this pass

- Rename/replace the authority path with `captureActivePageState()` that captures live Fabric overlay, connectors/images/labels, active table/cell edit value, page metadata, lock/group/z-order state, and updates `projectRef.current` synchronously.
- Save Now, Ctrl+S, autosave, page/tab switch, project open/upload, import, and export must use the same capture path.
- Backend must create project backups before overwrite and page-level snapshots after save, keeping latest 20.
- Recovery UI must show project backups, page snapshots, and local snapshots with object/table/connector counts and restore options.
- Table renderer must make normalized imported tables a reliable editable model, including Enter/Esc/Tab and right-click row/column/cell tools.
- Avoid internal scrollbars for printed table bodies; split/warn instead of clipping.
- Selection must explicitly support Ctrl/Shift multi-select, marquee, copy/paste/duplicate/delete/group/ungroup, and precise connector hit testing.
- Lock/unlock must be real: locked objects must not move, resize, rotate, edit text, delete, or change z-order unless unlocked/confirmed.
- Connector persistence must be protected: connectors serialize/reload with route points, style, labels, and lock state, and must not be filtered out.

## Root cause summary

The 3E pass made overlay/canvas saving safer, but the live editor still has multiple state authorities: Fabric canvas, contenteditable DOM table cells, React `project`, mutable `projectRef`, and backend `project.json`. The only synchronous pre-save capture currently covers Fabric overlay objects. Table cells, page metadata, active contenteditable state, and some structural page operations can still race save/navigation/export. The fix is to make active-page capture the single authority and force every save/navigation/export path through it before reporting success.
