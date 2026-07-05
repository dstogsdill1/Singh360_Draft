# BUGLIST_3C — Component Library + Editor Workflow Audit

Audit date: 2026-07-05. Scope: reconcile the "Final 3C Pass" spec against the
**actual** current codebase and record real broken/working state before coding.

> NOTE ON ARCHITECTURE DRIFT: the 3C spec references `ComponentLibrary.tsx` and
> `core/library_store.py`. Those still exist but are the **legacy** library. The
> live UI now uses `frontend/src/components/LibraryPanelV2.tsx` backed by
> `core/library_v2.py` (manifest-driven, routes under `/api/lib`). All fixes below
> target the **V2** system. `docs/BUGLIST_3E.md` already exists — this repo is
> past the point the 3C spec assumes.

## Phase A — Source / B&W Symbol / Both
- `insertUrlFor(c, rep)` returns source for `source`, else `symbolFile || sourceFile`.
- **BUG (confirmed):** the main **Insert** button calls
  `insertUrlFor(c, rep === 'both' ? 'symbol' : rep)` → in **Both** mode it inserts
  ONLY the symbol, never both objects. No side-by-side/stacked pair.
- **BUG:** B/W with no symbol previously silently inserted a grayscale source (no
  warning). Spec wants an explicit "No B/W symbol… insert Source instead?" prompt.
- Server `POST /api/lib/components/<id>/symbol` returns **400** (generator not
  enabled) — so real symbol generation is unavailable; B/W must fall back cleanly.
- Card preview (`CardPreview`) already honors Source/Symbol/Both correctly.

## Phase B — Open Component Builder
- `openComponentBuilder()` = `window.alert('Coming later …')`. **Still a stub.**
  (Deferred — see remaining-issues; the inline editor already covers rename/
  category/label/retire persistence, so this is lower priority than A/C/D.)

## Phase C — Category standard
- Categories come straight from `data.categories` (id/label/count) with no
  canonical display mapping or All-view filtering (reference/retired/needs-review
  are not hidden from All). **Partially broken vs spec.**

## Phase D — Inserted component labels
- `labelFor()` already returns `defaultLabel || partNumber || displayName` and
  suppresses labels for logos/markers/reference pages (`NO_LABEL_CATS`).
- `addComponent()` already inserts a separate Fabric `Textbox` below the image
  when a label is present, and both are independently selectable.
- Missing: object metadata (`componentId`, `sourceMode`, `assetPath`, …) and soft
  grouping of image+label. **Mostly working; metadata is the gap.**

## Phase E — Insert Image
- `addImage()` inserts full-res `FabricImage.fromURL` on the active page, selected,
  movable/resizable. **Working.** Uses full-res asset, not thumbnail.

## Phase F — Insert PDF page
- Routes exist: `POST /api/projects/<id>/pdf-thumbnails`,
  `/render-pdf-page`; V2 has `/api/lib/pdf/info` + `/api/lib/pdf/import`.
- Frontend `PdfInsertModal` + `uploadPdfForThumbnails`/`renderPdfPage` present.
  **Reported flaky** — needs a live smoke to confirm PyMuPDF availability +
  crisp render on export. Dependency check messaging to verify.

## Phase G — Text formatting
- Ribbon **Text** tab wires Bold/Italic/Underline/size/align/color to
  `onUpdateSelection`, disabled when no text is selected. **Working** (verify
  save/reload/export round-trip).

## Phase H — Snap guides / alignment
- `CanvasEditor` already builds transient `addVGuide`/`addHGuide` lines (excluded
  from export via `excludeFromExport`), snaps to page center + other object
  centers/edges + grid, threshold 8px, clears after move. **Working** (matches spec).

## Phase I — Table context tools
- Table/matrix right-click row/col ops exist and funnel through `onBlockChange` →
  autosave. **Believed working**; needs a persistence smoke.

## Phase J — Continuation controls
- Make Independent / Merge Into Previous / Exclude exist in App page ops.
  **Believed working**; "Try Fit on One Sheet"/"Recompose" are placeholders.

## Phase K — Placeholder / export cleanup
- `PrintView`/`NormalizedPage` gate editor-only drop zones with `data-noexport`
  and `.print-root [data-noexport] { display:none }`. **Working.**

## Phase L — Viewport stability
- Fit Page/Width recompute on panel collapse; internal-only scroll. **Believed OK.**

## Build / console
- `npm run build` green as of this session (bundle `index-DCR5LZWm.js`).
- Known non-blocking: 3 legacy thumbnail 404s in `smoke_component_library.py`
  (legacy store, not V2). Chunk-size >500kB warning (cosmetic).

## 3C priority order (this pass)
1. **Phase A** — real Source/B&W/Both + missing-symbol warning (the #1 complaint).
2. Phase D metadata (cheap, aids traceability).
3. Phase C category display map + All-view filtering.
Everything else is already working or is explicitly deferred (Component Builder
modal, PDF underlay/new-page insert modes).
