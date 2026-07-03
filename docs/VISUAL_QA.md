# Visual QA Checklist (manual)

Run the app, upload the SA31 workbook, and confirm each item. Reference the
SA31 / SA38 PDFs (see `docs/REFERENCE_INPUTS.md`) as visual targets — do not
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
- [ ] Paste a screenshot (Ctrl+V) on a canvas/hybrid page → image lands centered.
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
- [ ] Continuation pages show "… — CONTINUED" title.

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

- [ ] 1366×768 — shell + tabs + panels stay fixed.
- [ ] 1600×900 — OK.
- [ ] 1920×1080 — OK.
