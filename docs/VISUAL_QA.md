# Visual QA Checklist (manual)

Run the app, upload the SA31 workbook, and confirm each item. Reference the
SA31 / SA38 PDFs (see `docs/REFERENCE_INPUTS.md`) as visual targets â€” do not
pixel-copy them.

## Setup

```powershell
cd frontend; npm install; npm run build; cd ..
$env:SINGH360_PORT = 8766
python server.py
# open http://127.0.0.1:8766/app
```

## Pages

- [ ] Cover page looks like a cover (logo + project title), not a raw grid.
- [ ] Sheet Index (00_INDEX) renders as a clean index list, not a giant scroll grid.
- [ ] Sheet Index splits into `1.1`, `1.2`, ... if long.
- [ ] Project Scope renders as a text page (title + paragraphs + bullets).
- [ ] Responsibility Matrix renders as a structured matrix.
- [ ] Bill of Materials renders as a clean table with dark header row.
- [ ] Lighting Output Matrix renders as a clean table.
- [ ] Canvas pages (layout / one-line) show a clean editable canvas, no in-page mini buttons.
- [ ] Image/hybrid pages show "Image not attached" placeholder with Attach Image.

## Editing workflow

- [ ] Top page tabs can be dragged left/right to reorder.
- [ ] Reordering updates Page X of Y immediately.
- [ ] Excluded pages are not counted in Page X of Y.
- [ ] Left Output Pages up/down buttons still work and match tab order.
- [ ] Paste a screenshot (Ctrl+V) on a canvas/hybrid page â†’ image lands centered.
- [ ] Pasted image can be moved and resized with handles.
- [ ] Drag-drop an image file onto a canvas page places it.
- [ ] Selecting an image shows Selection Properties (fill/stroke/lock, etc.).
- [ ] Delete key removes the selected object.
- [ ] Undo / Redo work on canvas.

## Title block

- [ ] Title Block V2 appears on every page.
- [ ] Firm/logo area is compact (logo not oversized).
- [ ] Project / Location / File / Creator / Created / Edited By / Version / Date show.
- [ ] Sheet code + Page X of Y show.
- [ ] Continuation pages show "â€¦ â€” CONTINUED" title.

## Layout / print

- [ ] No output page has internal print scrollbars.
- [ ] Overflowing content splits into continuation pages or shows a layout warning badge.
- [ ] Export PDF uses `/app` print mode and includes pasted images.
- [ ] Fit Page / Fit Width / 100% behave predictably; whole browser does not scroll.

## CSV

- [ ] Uploading the Katy Park CSV attaches a CSV source.
- [ ] An Equipment Summary page is generated.
- [ ] Source view still shows raw CSV.

## Resolutions

- [ ] 1366Ã—768 â€” shell + tabs + panels stay fixed.
- [ ] 1600Ã—900 â€” OK.
- [ ] 1920Ã—1080 â€” OK.

## Milestone 2E — editor hardening

- [ ] Page template dropdown shows friendly names (Cover, Text / Instructions, Table / Schedule, Matrix, Image / Layout, Hybrid Sheet, Underlay / Reference, Sheet Index). No "index" / "canvas" / "data-grid".
- [ ] Ctrl+V pastes a screenshot on ANY page (cover, text, matrix, table), auto-enables Overlay edit, selects the image with handles.
- [ ] Pasted screenshot auto-named "Screenshot YYYY-MM-DD HH-mm-ss.png".
- [ ] Drag/drop an image onto any page inserts it.
- [ ] "Edit Overlay" toggle (Home tab) turns overlay editing on/off; base content is clickable when off.
- [ ] Double-click a top page tab renames the sheet title (Enter save, Esc cancel); left list, right panel, page heading, title block all update.
- [ ] Double-click sheet code / title in the left Output Pages list edits inline.
- [ ] Renumber Sheet Codes opens a modal with Old/New/Title preview and Keep / Sequential / Custom-prefix schemes; Apply updates tabs, left list, title block.
- [ ] Continuation pages show a badge + "Make independent" button in the left list.
- [ ] Title Block V3/V4 looks like an issued drawing (firm block, project block, revision block, sheet code, Sheet X of Y, CONTINUED marker).
- [ ] Right panel shows Project Folder, Assets Folder, Screenshots folder paths.
- [ ] Collapse both side panels; drawing area expands; reopen with rail buttons.
- [ ] Every ribbon button is enabled+working, or disabled with a "Coming soon" tooltip.
- [ ] Save, reload browser: overlays, titles, codes, order all persist.
- [ ] Export PDF includes pasted screenshots and edits.
- [ ] Export Package ZIP includes project.json, manifest.json, sources, assets, exports.

### Known partial / coming soon (2E)
- Rich text / table formatting toolbar (Phase E): bold/align exist on contenteditable via browser only; dedicated ribbon controls are "Coming soon".
- Full Layers panel (Phase J): overlay is a single annotation layer; per-layer lock/visibility is "Coming soon".
- Asset Manager list with rename-file / insert-on-page / delete (Phase N): folder paths are shown; full list UI is "Coming soon".
- Right-click context menu paste: use Ctrl+V (browser clipboard-image limitation).
- Align / distribute buttons (Arrange tab): "Coming soon".

## Milestone 3B punch list — editor polish

- [ ] Export ? paper size modal: 11×17 default, Letter, ANSI B–E, Arch B–E, Custom + orientation; title block not clipped.
- [ ] Insert ? Image: pick a PNG/JPG (e.g. H-E-B logo) on the cover; full-res, resizable; drag to center (snap guide appears).
- [ ] Snap guides: drag an object near page center ? pink center guide appears and snaps; align two objects ? guide appears.
- [ ] Component Library: "Auto-categorize" button re-buckets by part name; ? edit renames/recategorizes and persists; "Show retired" + Restore; "Insert with label" adds an editable label for equipment (off for logos/symbols).
- [ ] Drag a component onto a page ? image + label land on the ACTIVE page only; switch pages ? it does not leak.
- [ ] Text tab: select a text box ? Bold / Italic / Underline / A- A+ / Align L·C·R / Color all work; save/reload/export.
- [ ] Image/Layout empty page shows a drop zone in the editor but exports with NO placeholder text.
- [ ] Toggle both side panels ? sheet stays in frame, Fit Page recomputes.

### Known deferred (3B)
- Insert ? PDF page render (needs PyMuPDF/PDF.js) — not implemented; use Insert ? Image of a schematic crop for now.
- Continuation auto-fit/recompose — merge / make-independent exist; automatic shrink-to-fit does not.
- Component label is a separate object (not grouped/linked) — editable/removable independently.
- Auto-categorize cannot fix wrong extraction NAMES (e.g. a contactor named "PR0650"); rename via ?.
