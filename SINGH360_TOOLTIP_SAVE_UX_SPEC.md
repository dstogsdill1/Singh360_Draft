# Singh360 Draft — Complete Tooltip Coverage and Clear Save-State UX

## Purpose

Make Singh360 Draft explain itself everywhere.

A user should be able to hover over or keyboard-focus any control, status, icon, tab, page action, table action, canvas object action, Data Workspace control, Excel Layout control, or disabled command and immediately understand:

1. what the item is;
2. what it does;
3. what data it changes;
4. whether it saves only to the local Singh360 project or also writes the linked Excel workbook;
5. why it is disabled or unavailable;
6. what the user should do next.

This is an application-wide usability repair. It must not change engineering content, workbook authority rules, page publishing rules, or customer data.

---

## Live repository and protected starting evidence

Repository expected on this computer:

`C:\Users\DarrinStogsdill\OneDrive - Homeland Development Services LLC\Desktop\Singh360_Draft`

GitHub origin:

`https://github.com/dstogsdill1/Singh360_Draft.git`

Last known protected Excel Layout implementation commit:

`419b47735dbe8ee264ac7c2fad175ac7027f409e`

Last known protected Excel Layout backup:

`.docs\patch_backups\excel_layout_canvas_20260728_064900`

Do not assume those are still the live branch or HEAD. Before editing, discover and record the actual current branch, HEAD, upstream, Git status, staged diff, unstaged diff, and origin. Stay on the current branch.

---

# 1. Non-negotiable safety rules

1. `.docs` is production data. Never delete, reset, clean, normalize, rebuild, or commit it.
2. Never run `git reset`, `git stash`, `git clean`, destructive checkout, force push, or any command that discards existing work.
3. Preserve all existing staged, unstaged, and untracked user work.
4. Before changing source:
   - create `.docs\patch_backups\tooltip_save_ux_<timestamp>`;
   - copy every source file that will be changed;
   - back up the complete active project package;
   - back up the linked workbook;
   - record branch, HEAD, upstream, Git status, staged diff, and unstaged diff.
5. Never run **SAVE + WRITE EXCEL** against a live customer workbook during development. Use a protected clone.
6. Preserve:
   - Project Home;
   - Visual Page Manager;
   - Data Workspace;
   - existing local autosave;
   - SAVE + WRITE EXCEL;
   - Excel Layout pages;
   - Component Library;
   - Symbol Mapper;
   - Symbol Legend builder;
   - PDF crop;
   - canvas objects;
   - pasted images;
   - connectors;
   - legends;
   - annotations;
   - the 829 project and workbook;
   - PDF export.
7. Do not weaken two-sided workbook conflict detection.
8. Existing flow pages that do not use Excel Layout must behave exactly as before.
9. Do not invent engineering data, workbook values, page codes, controller IDs, IP addresses, quantities, dates, scope, or notes.
10. Do not claim success without direct test evidence.

---

# 2. Diagnose the unsaved-workspace problem before patching

Search the live source for the exact visible message:

`Unsaved workspace edits`

Then trace, in the actual current code:

- the state variable or derived selector that produces it;
- every place that sets the state dirty;
- every local-save handler;
- every autosave handler;
- every Data Workspace save handler;
- every project reload or server-echo path;
- every workbook-sync state;
- `beforeunload` or navigation guards;
- page/project hashes and revision counters;
- the response that confirms a successful local save.

Write the diagnosis into the closeout report before implementing the fix.

Do not hide the warning. Fix the state logic so the warning is truthful.

## Required save-state behavior

The UI must distinguish these states:

| State | Exact visible label | Meaning |
|---|---|---|
| `cleanLocal` | `PROJECT SAVED` | Current in-memory project matches the last confirmed local save. |
| `dirtyLocal` | `UNSAVED PROJECT EDITS` | At least one current in-memory edit is not yet confirmed saved locally. |
| `dirtyWorkspace` | `UNSAVED WORKSPACE EDITS` | Data Workspace edits are in memory and not yet confirmed saved into the local Singh360 project. |
| `savingLocal` | `SAVING PROJECT…` | A local save request is in flight. |
| `localSavedSyncPending` | `PROJECT SAVED · WORKBOOK SYNC PENDING` | Local project is saved; linked Excel does not yet contain the latest app changes. |
| `writingWorkbook` | `SAVING PROJECT + WRITING EXCEL…` | Local save succeeded and the workbook mirror is currently running. |
| `savedAndSynced` | `PROJECT SAVED · WORKBOOK SYNCED` | Local project and linked workbook are confirmed synchronized. |
| `saveFailed` | `SAVE FAILED` | The local save request failed. Dirty state must remain. |
| `syncFailed` | `WORKBOOK SYNC FAILED` | Local project may be saved, but Excel mirror failed. Do not clear sync pending. |
| `conflict` | `PROJECT / WORKBOOK CONFLICT` | Both sides changed. Neither side may be overwritten automatically. |

## Required dirty-state rules

1. Loading a project establishes a clean baseline and must not immediately mark it dirty.
2. A server echo, normalization pass, render-only update, selected page change, zoom change, panel open/close, hover, tooltip, or active-tab change must not mark project content dirty.
3. A genuine content edit must mark the correct dirty domain.
4. Local dirty state may clear only after the server confirms the save for the same project revision/hash that was submitted.
5. If another edit happens while a save is in flight, the save response must not clear the newer edit.
6. Saving Data Workspace edits must clear `dirtyWorkspace` only after a confirmed local project save.
7. Local save must not falsely mark the workbook synchronized.
8. Workbook sync pending is not the same as unsaved local work.
9. `beforeunload` must warn only for genuine unconfirmed local edits, not merely because workbook sync is pending.
10. Failed saves retain dirty state and show the actual error.
11. Display `Last local save: <time>` and, separately, `Last workbook sync: <time>` when known.
12. Add a `What is unsaved?` action that lists the dirty domains, such as:
    - Data Workspace cells;
    - page metadata;
    - page order;
    - canvas objects;
    - Excel Layout tables;
    - title block or project metadata;
    - component/legend placement.
13. Do not fabricate dirty details. Populate the list from the actual change tracking.
14. `Ctrl+S`, when not captured by a cell editor, must run local project save only.
15. The explicit green **SAVE + WRITE EXCEL** command remains the only full workbook mirror action.

---

# 3. Tooltip architecture — implement once, use everywhere

Create one reusable, accessible tooltip system. Do not scatter ad hoc browser `title` attributes through the code.

Preferred source structure:

- `frontend/src/components/help/AppTooltip.tsx`
- `frontend/src/components/help/TooltipProvider.tsx` if a provider is needed
- `frontend/src/components/help/tooltipRegistry.ts`
- `frontend/src/components/help/TooltipAudit.ts`
- `frontend/src/styles/tooltips.css`
- focused tests for registry and browser behavior

First inspect `package.json`. Reuse an installed accessible tooltip library only if it is already present and used. Do not add a large UI framework for this repair.

## Tooltip behavior

Every tooltip must:

- appear after about 350 ms on mouse hover;
- appear immediately on keyboard focus;
- close on mouse leave, blur, or Escape;
- stay open long enough to read;
- use `aria-describedby`;
- never steal the click;
- never block dragging;
- render above modals, canvas overlays, and sidebars;
- reposition to remain inside the viewport;
- support top, bottom, left, and right placement;
- have a maximum readable width around 320–380 px;
- wrap text;
- work at browser zoom from 80% through 200%;
- work in light and dark app surfaces if both exist;
- use a wrapper for disabled buttons so the explanation is still hoverable/focusable;
- avoid layout shift;
- not create thousands of permanent tooltip nodes for worksheet cells.

For high-density cells and canvas objects, use one delegated/shared tooltip that is populated from the hovered target.

## Required data attributes

Every actionable or status-bearing element must have a stable help ID:

`data-help-id="save.writeExcel"`

The tooltip copy must come from `tooltipRegistry.ts`, not be duplicated in JSX.

Every tooltip registry entry must contain:

```ts
type TooltipDefinition = {
  title: string;
  body: string;
  saveScope?: "none" | "local-project" | "linked-workbook" | "export-only";
  disabledReason?: string | ((context) => string);
  shortcut?: string;
};
```

Tooltips may show a small scope line:

- `Changes: none`
- `Saves to: local Singh360 project`
- `Writes: linked Excel workbook`
- `Creates: exported file only`

## Coverage rule

Add tooltip coverage to every current:

- `button`;
- icon button;
- menu button;
- menu item;
- tab;
- toggle;
- checkbox;
- radio control;
- input;
- select;
- textarea;
- color picker;
- range slider;
- status chip;
- warning banner;
- page pill;
- drag handle;
- resize handle;
- table header action;
- cell editor action;
- page action;
- modal action;
- object action;
- disabled command;
- ambiguous label;
- terse abbreviation;
- save/sync indicator.

Plain paragraphs do not need redundant tooltips. Interactive drawing cells and objects do.

---

# 4. Exact tooltip copy registry

Use these IDs and meanings. Adjust only wording needed to match a verified current behavior. Do not alter behavior merely to match copy.

## A. Project Home and project cards

| Help ID | Title | Required body |
|---|---|---|
| `project.new` | New project | Creates a new local Singh360 project. It does not create or modify an Excel workbook until one is linked and Save + Write Excel is used. |
| `project.open` | Open project | Opens the selected local Singh360 project package and its saved editor state. |
| `project.importWorkbook` | Import workbook | Creates or refreshes a Singh360 project from a selected workbook using the controlled import workflow. The source workbook must not be edited at the same time. |
| `project.recentCard` | Recent project | Opens this project. The card status describes local-save and workbook-link state. |
| `project.openFolder` | Open project folder | Opens the local project package folder in File Explorer. This does not save or sync anything. |
| `project.linkWorkbook` | Link workbook | Associates this Singh360 project with an Excel workbook. Linking does not write to the workbook. |
| `project.relinkWorkbook` | Change linked workbook | Selects a different workbook link. Verify that the selected workbook belongs to this project before continuing. |
| `project.refreshWorkbook` | Refresh from workbook | Reads eligible workbook changes into the project only when conflict rules allow it. It does not bypass two-sided conflict protection. |
| `project.backup` | Back up project | Creates a recoverable project-package backup before risky work. |
| `project.delete` | Remove project | Removes the selected local project only after confirmation. It must not silently delete the linked workbook. |
| `project.status.noWorkbook` | No workbook linked | The project can be edited locally, but Save + Write Excel is unavailable until a workbook is linked. |
| `project.status.linked` | Workbook linked | This project has a linked workbook. Linking alone does not mean the workbook is synchronized. |
| `project.status.syncPending` | Workbook sync pending | The local project contains confirmed saved changes that have not yet been mirrored to the linked workbook. |
| `project.status.conflict` | Project/workbook conflict | Both the local project and workbook changed since the last confirmed sync. Do not overwrite either side until the conflict workflow resolves it. |

## B. Global navigation and status

| Help ID | Title | Required body |
|---|---|---|
| `nav.projectHome` | Project Home | Returns to the project dashboard. Unsaved local edits must be saved or explicitly handled before leaving. |
| `nav.pageManager` | Visual Page Manager | Opens the full-screen page organizer for inclusion, order, page codes, titles, and page actions. |
| `nav.componentLibrary` | Component Library | Opens reusable symbols, components, plan markers, callouts, safety signs, and saved legends. |
| `nav.symbolMapper` | Symbol Mapper | Finds supported symbols on an existing drawing and applies the approved map highlights. |
| `nav.help` | Help | Opens application guidance. Tooltips remain available while help is open. |
| `status.localSaved` | Project saved | The current project state is confirmed saved locally. This does not prove the linked workbook is current. |
| `status.unsavedProject` | Unsaved project edits | One or more project edits have not yet been confirmed saved locally. Open What is unsaved? for details. |
| `status.unsavedWorkspace` | Unsaved workspace edits | Data Workspace changes exist in memory and are not yet confirmed saved to the local Singh360 project. |
| `status.syncPending` | Workbook sync pending | The project is locally saved, but the linked workbook still needs Save + Write Excel. |
| `status.conflict` | Project/workbook conflict | Both sides changed. Automatic overwrite is blocked to protect data. |
| `status.whatUnsaved` | What is unsaved? | Lists the actual dirty areas currently waiting for local save. |
| `status.lastLocalSave` | Last local save | Shows when the project was last confirmed saved to the local Singh360 package. |
| `status.lastWorkbookSync` | Last workbook sync | Shows when Save + Write Excel last completed successfully. |

## C. Save and export

| Help ID | Title | Required body |
|---|---|---|
| `save.localProject` | Save project | Saves current editor and Data Workspace changes to the local Singh360 project. It does not write the linked Excel workbook. |
| `save.workspace` | Save workspace edits | Saves Data Workspace cell and structure changes into the local Singh360 project. The unsaved marker clears only after confirmation. |
| `save.writeExcel` | Save + Write Excel | Saves the local project first, then mirrors controlled workbook data, 00_INDEX, tabs, order, codes, titles, inclusion, status colors, and workbook-backed page data to the linked workbook. Close Excel before running it. |
| `save.autosave` | Local autosave | Singh360 periodically saves the local project. Workbook sync remains explicit. |
| `save.retry` | Retry save | Retries the failed local save without discarding current edits. |
| `save.resolveConflict` | Resolve conflict | Opens the protected conflict workflow. It must not force an overwrite. |
| `export.pdf` | Export PDF | Creates a PDF drawing package from included published pages. It does not modify the workbook. |
| `export.projectPackage` | Export project package | Creates a portable Singh360 project package containing the project state and approved assets. |
| `export.worksheet` | Export worksheet | Creates a standalone worksheet export from the current app-managed page without changing the linked workbook. |

## D. Page sidebar and navigation

| Help ID | Title | Required body |
|---|---|---|
| `pages.search` | Search pages | Filters the page list by code, title, tab, family, type, or status. |
| `pages.filter` | Filter pages | Shows only pages matching the selected inclusion, status, family, or type filter. |
| `pages.clearFilter` | Clear page filters | Returns the sidebar to all available pages. |
| `pages.pagePill` | Published page number | Shows the page’s published position among included drawing pages. Excluded pages do not count. |
| `pages.active` | Active page | This is the page currently shown in the editor. |
| `pages.include` | Include in drawing | Controls whether this base page publishes. Only explicit Include/Yes/True rows publish. |
| `pages.exclude` | Exclude from drawing | Keeps the source/reference page available but removes it from the published package. |
| `pages.dragReorder` | Reorder page | Drag to change base-page order. Cover remains first and Sheet Index/TOC remains second. |
| `pages.previous` | Previous page | Opens the previous page that matches the current filter. |
| `pages.next` | Next page | Opens the next page that matches the current filter. |
| `pages.moreActions` | Page actions | Opens rename, duplicate, include/exclude, type, status, and delete actions available for this page. |
| `pages.duplicate` | Duplicate page | Creates a new base page from this page while preserving the original. |
| `pages.delete` | Delete app page | Deletes only after confirmation and must preserve protected source/reference behavior. |
| `pages.rename` | Rename page | Changes the app page title and, when mirrored, the controlled workbook title fields. |
| `pages.sheetCode` | Sheet code | The drawing-package code controlled by 00_INDEX for a base page. |
| `pages.sheetTab` | Worksheet tab | The workbook worksheet name linked to this base page. |

## E. View controls

| Help ID | Title | Required body |
|---|---|---|
| `view.normalized` | Normalized view | Shows the Singh360 page rendering produced from structured project data. |
| `view.source` | Source view | Shows the preserved source worksheet/page representation for comparison. |
| `view.canvas` | Canvas view | Opens the editable drawing-object canvas for manual layouts and overlays. |
| `view.excelLayout` | Excel Layout | Places independent editable tables on a real 11 × 17 canvas and exports them as real Excel cells. |
| `view.fitWidth` | Fit width | Fits the active page width in the available editor area. |
| `view.fitPage` | Fit page | Fits the entire 11 × 17 page in the editor. |
| `view.zoom100` | Actual size | Displays the page at 100% editor zoom. |
| `view.zoomIn` | Zoom in | Magnifies the editor view without changing exported dimensions. |
| `view.zoomOut` | Zoom out | Reduces the editor view without changing exported dimensions. |
| `view.printBoundary` | Printable boundary | The dotted line marks the area intended to remain inside the printed 11 × 17 page. |
| `view.continuationPage` | Continuation page | This page is generated from overflow. It must not create a duplicate base row in 00_INDEX. |
| `view.printMode` | Print preview | Hides editing chrome and previews the published page output. |

## F. Ribbon and editing commands

| Help ID | Title | Required body |
|---|---|---|
| `edit.undo` | Undo | Reverses the most recent supported editor action. |
| `edit.redo` | Redo | Restores the most recently undone action. |
| `edit.cut` | Cut | Removes the selected editable item and places it on the clipboard. |
| `edit.copy` | Copy | Copies the selected item without removing it. |
| `edit.paste` | Paste | Pastes supported clipboard content. Excel, HTML, CSV, and TSV tables must remain editable tables where supported. |
| `edit.duplicate` | Duplicate | Creates a movable copy of the selected object or table. |
| `edit.delete` | Delete selection | Removes the selected editable object after applying current confirmation rules. |
| `insert.text` | Insert text | Adds an editable text object to the current page. |
| `insert.table` | Insert table | Adds a real editable table, not a screenshot or flat text note. |
| `insert.image` | Insert image | Adds an image object that can be moved, resized, bordered, shadowed, and saved with the project. |
| `insert.pdfCrop` | Insert PDF crop | Opens the precision crop tool and inserts the selected PDF region as a movable page object. |
| `insert.component` | Insert component | Opens the Component Library for direct insertion of a reusable component. |
| `insert.symbolLegend` | Insert symbol legend | Builds or inserts an editable saved legend using approved component assets. |
| `insert.connector` | Insert connector | Adds a line or connector between drawing objects. |
| `insert.callout` | Insert callout | Adds a numbered or labeled callout object. |
| `arrange.front` | Bring to front | Moves the selected object above all overlapping objects. |
| `arrange.forward` | Bring forward | Moves the selected object one layer upward. |
| `arrange.backward` | Send backward | Moves the selected object one layer downward. |
| `arrange.back` | Send to back | Moves the selected object behind all overlapping objects. |
| `arrange.alignLeft` | Align left | Aligns selected objects to a common left edge. |
| `arrange.alignCenter` | Align centers | Aligns selected objects to a common horizontal center. |
| `arrange.alignRight` | Align right | Aligns selected objects to a common right edge. |
| `arrange.alignTop` | Align top | Aligns selected objects to a common top edge. |
| `arrange.alignMiddle` | Align middles | Aligns selected objects to a common vertical center. |
| `arrange.alignBottom` | Align bottom | Aligns selected objects to a common bottom edge. |
| `arrange.distributeHorizontal` | Distribute horizontally | Spaces selected objects evenly from left to right. |
| `arrange.distributeVertical` | Distribute vertically | Spaces selected objects evenly from top to bottom. |
| `arrange.snap` | Snap | Snaps movement and resizing to supported page, grid, and object guides. |
| `arrange.guides` | Alignment guides | Shows temporary PowerPoint-style guides while moving or resizing objects. |

## G. Properties panel and canvas objects

| Help ID | Title | Required body |
|---|---|---|
| `object.select` | Select object | Click to select. Drag to move. Use handles to resize or rotate when supported. |
| `object.lock` | Lock object | Prevents accidental movement or resizing while keeping the object visible. |
| `object.positionX` | Horizontal position | Sets the object’s left position on the 11 × 17 page. |
| `object.positionY` | Vertical position | Sets the object’s top position on the 11 × 17 page. |
| `object.width` | Object width | Changes the selected object’s width. |
| `object.height` | Object height | Changes the selected object’s height. |
| `object.rotation` | Rotation | Rotates the selected object by the specified angle. |
| `object.opacity` | Opacity | Changes object transparency without changing the source asset. |
| `object.border` | Border | Adds or changes the visible border around the selected image or PDF crop. |
| `object.borderWidth` | Border width | Sets the selected object’s border thickness. |
| `object.borderColor` | Border color | Sets the selected object’s border color. |
| `object.shadow` | Shadow | Adds or removes a drop shadow from the selected image or PDF crop. |
| `object.shadowBlur` | Shadow blur | Controls how soft the object shadow appears. |
| `object.shadowOffset` | Shadow offset | Controls how far the shadow moves from the object. |
| `object.crop` | Edit crop | Reopens crop controls for the selected supported image or PDF crop. |
| `object.group` | Group | Treats selected objects as one movable unit while preserving their contents. |
| `object.ungroup` | Ungroup | Returns a group to independently editable objects. |

## H. Data Workspace

Add tooltips to every actual Data Workspace control. Use the following IDs where the matching control exists.

| Help ID | Title | Required body |
|---|---|---|
| `workspace.open` | Data Workspace | Opens workbook-backed page data for structured editing inside Singh360. |
| `workspace.sheetSelector` | Workspace sheet | Selects the page or worksheet data being edited. Switching views does not automatically write Excel. |
| `workspace.cell` | Workspace cell | Click to select this cell. Editing changes the local workspace state until Save Workspace Edits confirms a local save. |
| `workspace.cellAddress` | Cell address | Shows the selected worksheet-style row and column reference. |
| `workspace.formulaBar` | Cell value editor | Edits the selected cell value or formula text supported by the workspace model. |
| `workspace.addRow` | Add row | Inserts a row in the app-managed workspace data. Save locally before leaving. |
| `workspace.deleteRow` | Delete row | Removes the selected app-managed row after confirmation. |
| `workspace.addColumn` | Add column | Inserts a column in the app-managed workspace data. |
| `workspace.deleteColumn` | Delete column | Removes the selected app-managed column after confirmation. |
| `workspace.merge` | Merge cells | Combines the selected valid cell range into one displayed cell. |
| `workspace.unmerge` | Unmerge cells | Separates the selected merged range into individual cells. |
| `workspace.wrap` | Wrap text | Displays long text on multiple lines inside the selected cell or range. |
| `workspace.bold` | Bold | Toggles bold formatting for the selected editable cell or range. |
| `workspace.italic` | Italic | Toggles italic formatting for the selected editable cell or range. |
| `workspace.underline` | Underline | Toggles underline formatting for the selected editable cell or range. |
| `workspace.fill` | Cell fill | Changes the selected cell or range background fill. |
| `workspace.fontColor` | Font color | Changes text color in the selected cell or range. |
| `workspace.border` | Cell borders | Changes border placement and style for the selected cell or range. |
| `workspace.rowHeight` | Row height | Changes the selected app-managed row height. |
| `workspace.columnWidth` | Column width | Changes the selected app-managed column width. |
| `workspace.pasteTable` | Paste table | Pastes Excel, HTML, CSV, or TSV cells as structured editable workspace cells. |
| `workspace.reload` | Reload saved workspace | Reloads the last confirmed local project state. Warn before replacing genuine unsaved edits. |
| `workspace.discard` | Discard workspace edits | Reverts only genuine unconfirmed Data Workspace edits after explicit confirmation. |
| `workspace.save` | Save workspace edits | Saves current workspace edits into the local Singh360 project. It does not write the linked workbook. |
| `workspace.syncExcel` | Save + Write Excel | Saves locally first, then mirrors approved workbook-backed changes through the protected full workbook workflow. |
| `workspace.unsavedBadge` | Unsaved workspace edits | This badge remains until the current workspace revision is confirmed saved locally. |
| `workspace.savedBadge` | Workspace saved | The current workspace revision is confirmed saved in the local Singh360 project. |
| `workspace.sourceRange` | Source range | Shows the preserved workbook range associated with this workspace region when available. |
| `workspace.protectedCell` | Protected source cell | This source-backed cell cannot be changed through the current workspace action. The tooltip must state the actual reason. |

### Dynamic cell tooltip

Use one delegated tooltip for cells:

`Cell {address}. Click to select; double-click or press Enter to edit. Current changes save to the local Singh360 project with Save Workspace Edits and reach Excel only through Save + Write Excel.`

For protected/readonly cells, replace the edit sentence with the actual verified reason.

## I. Excel Layout mode

| Help ID | Title | Required body |
|---|---|---|
| `excelLayout.enable` | Enable Excel Layout | Converts or enables this app page for independent editable table placement on the 11 × 17 canvas. |
| `excelLayout.addTable` | Add table | Adds a new independently sized and positioned editable table. |
| `excelLayout.pasteTable` | Paste table | Creates a new editable table from Excel, HTML, CSV, or TSV clipboard data. |
| `excelLayout.table` | Excel Layout table | This table has its own position, dimensions, columns, rows, merges, title, styles, and overflow behavior. |
| `excelLayout.tableTitle` | Table title | Sets the first-class merged title printed above this table. It is not a fake body row. |
| `excelLayout.mergeTitle` | Merge title across table | Merges the exported Excel title cell across this table’s visible width. |
| `excelLayout.columnWidth` | Table column width | Resizes this table’s column only. It must not change an unrelated table above or below it. |
| `excelLayout.rowHeight` | Table row height | Changes the selected row height and exported editable-cell geometry. |
| `excelLayout.keepTogether` | Keep together | Moves the table to the next 11 × 17 page when it fits there as one unit. |
| `excelLayout.splitRows` | Split rows | Allows overflow to continue on later pages, splitting only at valid row boundaries. |
| `excelLayout.repeatTitle` | Repeat table title | Repeats the merged table title on continuation pages. |
| `excelLayout.repeatHeaders` | Repeat column headers | Repeats the table’s column header row on continuation pages. |
| `excelLayout.tabColor` | Workbook tab color | Sets the custom worksheet tab color for this included page. Excluded-page gray still overrides it. |
| `excelLayout.pageBoundary` | 11 × 17 page boundary | Marks one Tabloid landscape page. Moving content below it creates a continuation page. |
| `excelLayout.printableBoundary` | Printable area | Keep critical content inside this dotted boundary to avoid printer clipping. |
| `excelLayout.continuationIdentity` | Continuation identity | Shows the generated continuation segment. It does not create a duplicate 00_INDEX base row. |

## J. Visual Page Manager

| Help ID | Title | Required body |
|---|---|---|
| `pageManager.open` | Visual Page Manager | Opens the full-screen page organizer. |
| `pageManager.tile` | Page tile | Selects this page and shows its current include, code, title, type, and status. |
| `pageManager.drag` | Reorder page | Drag the tile to change base-page order. Protected Cover and Sheet Index positions remain enforced. |
| `pageManager.include` | Publish this page | Includes the base page in the drawing package and published page numbering. |
| `pageManager.exclude` | Keep as source/reference | Keeps the page available but removes it from published page numbering and output. |
| `pageManager.autoScroll` | Active-page tracking | Automatically scrolls the manager so the active page tile remains visible. |
| `pageManager.save` | Save page changes | Saves page order and metadata to the local project. Workbook mirroring remains explicit. |
| `pageManager.close` | Close Page Manager | Returns to the editor. Warn only when genuine unsaved page-manager edits remain. |

## K. PDF crop

| Help ID | Title | Required body |
|---|---|---|
| `pdfCrop.source` | PDF source | Selects the source PDF and page used for this crop. |
| `pdfCrop.page` | PDF page | Changes the source PDF page without changing the crop already saved until Apply is used. |
| `pdfCrop.zoom` | Crop zoom | Magnifies the source view for precise selection. It does not change output resolution by itself. |
| `pdfCrop.pan` | Pan source | Moves the PDF beneath the crop viewport without changing the selected dimensions. |
| `pdfCrop.rotateLeft` | Rotate left | Rotates the crop 90° counterclockwise. |
| `pdfCrop.rotateRight` | Rotate right | Rotates the crop 90° clockwise. |
| `pdfCrop.exactWidth` | Exact crop width | Sets the crop width using the supported page measurement system. |
| `pdfCrop.exactHeight` | Exact crop height | Sets the crop height using the supported page measurement system. |
| `pdfCrop.highDpi` | High-resolution crop | Creates the inserted crop at high enough resolution for drawing-package output. |
| `pdfCrop.apply` | Insert crop | Inserts the selected crop as a separate movable canvas object and saves it with the project after local save. |
| `pdfCrop.cancel` | Cancel crop | Closes the crop tool without inserting the pending crop. |

## L. Component Library, symbols, and legends

| Help ID | Title | Required body |
|---|---|---|
| `library.search` | Search components | Filters the Component Library by name, code, category, collection, alias, or description. |
| `library.collection` | Component collection | Shows only components in the selected saved collection. |
| `library.category` | Component category | Filters components by category without changing the saved component. |
| `library.card` | Component card | Shows the saved reusable component. Use Direct Insert to place a separate movable object. |
| `library.directInsert` | Direct insert | Places this exact saved component on the active page as a separate movable object. |
| `library.favorite` | Favorite | Adds or removes this component from favorites without changing the source asset. |
| `library.edit` | Edit component | Opens supported metadata or reusable-object editing. It must not silently alter existing placed copies. |
| `library.delete` | Delete saved component | Removes the saved library entry only after confirmation. It must not remove existing placed objects. |
| `library.saveLegend` | Save legend | Saves the current editable legend as a reusable Component Library entry. |
| `legend.builder` | Symbol Legend builder | Builds an editable legend from selected approved symbols. |
| `legend.row` | Legend row | Represents one symbol and its verified description. |
| `legend.insertSeparate` | Insert selected symbols separately | Inserts each selected legend symbol as an independent movable object. |
| `symbolMapper.scan` | Scan page symbols | Searches the active source drawing for supported symbol occurrences. |
| `symbolMapper.include` | Include match | Marks this verified occurrence for approved map highlighting. |
| `symbolMapper.ignore` | Ignore match | Excludes this occurrence from generated highlights without deleting source content. |
| `symbolMapper.apply` | Apply highlights | Places approved component highlights on included verified occurrences. |

## M. Recovery, cleanup, warnings, and dialogs

| Help ID | Title | Required body |
|---|---|---|
| `recovery.openBackup` | Open backup | Opens a selected project backup for inspection or controlled recovery. |
| `recovery.restore` | Restore backup | Restores the selected backup only after showing the exact target and required confirmation. |
| `recovery.cancel` | Cancel recovery | Closes recovery without changing project data. |
| `workspaceCleanup.open` | Workspace cleanup | Opens the existing cleanup workflow. The tooltip must name exactly what it can remove and what it preserves. |
| `workspaceCleanup.preview` | Preview cleanup | Shows proposed cleanup actions before any change. |
| `workspaceCleanup.confirm` | Confirm cleanup | Executes only the previewed cleanup after protected backup and confirmation. |
| `dialog.confirm` | Confirm action | Executes the action described in this dialog. |
| `dialog.cancel` | Cancel | Closes the dialog without applying the pending action. |
| `dialog.close` | Close dialog | Closes this window. Warn only if genuine unsaved dialog edits would be lost. |
| `warning.disabled` | Command unavailable | Explain the current verified reason the command is disabled and what prerequisite enables it. |

---

# 5. Required component coverage map

Inspect the current live tree and apply tooltips to the actual components. At minimum review and update these current areas when present:

- `frontend/src/App.tsx`
- `frontend/src/components/ProjectDashboard.tsx`
- `frontend/src/components/Ribbon.tsx`
- `frontend/src/components/PageNavigator.tsx`
- `frontend/src/components/DocumentView.tsx`
- `frontend/src/components/PageRenderer.tsx`
- `frontend/src/components/CanvasEditor.tsx`
- `frontend/src/components/PropertiesPanel.tsx`
- `frontend/src/components/PageManagerModal.tsx`
- `frontend/src/components/PdfCropModal.tsx`
- `frontend/src/components/LibraryPanelV2.tsx`
- `frontend/src/components/CleanWorkspaceModal.tsx`
- `frontend/src/components/BackupRecoveryModal.tsx`
- `frontend/src/components/renderers/NormalizedPage.tsx`
- `frontend/src/components/renderers/RawGridRenderer.tsx`
- every current Excel Layout component introduced by commit `419b477` or later
- every current modal, toolbar, popup, menu, and status component discovered by the audit

Do not blindly modify a file merely because it is listed. Verify it exists and contains the relevant live controls.

---

# 6. Tooltip audit and enforcement

Create a reusable audit that can run in development and browser smoke tests.

It must inspect visible elements matching:

```css
button,
[role="button"],
[role="tab"],
[role="menuitem"],
input,
select,
textarea,
[draggable="true"],
[data-action],
[data-status-chip],
[data-page-pill],
[data-resize-handle]
```

A visible actionable/status element fails coverage unless it has:

- a valid `data-help-id`;
- a matching non-empty registry entry;
- an accessible name;
- keyboard focus where appropriate.

Document narrowly justified exemptions in code. Do not broadly exempt entire components.

Expose a development-only helper such as:

`window.__S360_TOOLTIP_AUDIT__()`

It should return:

- total visible targets;
- covered targets;
- missing help IDs;
- invalid registry IDs;
- duplicate IDs where uniqueness is required;
- inaccessible controls.

It must not exist or expose sensitive data in production unless the current app already supports a safe diagnostics surface.

---

# 7. Required visual behavior

- Tooltips use Singh360 visual language, not browser-default yellow boxes.
- Dark charcoal or near-black background.
- High-contrast white text.
- Optional small orange title/accent.
- Rounded corners.
- Subtle shadow.
- Clear arrow when placement permits.
- No tooltip may cover the control being explained.
- Tooltip must not be clipped by:
  - sidebar;
  - ribbon;
  - modal;
  - Visual Page Manager;
  - PDF crop viewport;
  - canvas;
  - Data Workspace grid;
  - Component Library.
- Avoid opening multiple tooltips simultaneously.
- Do not animate in a distracting way.
- Keep title concise and body usually one to three sentences.
- Dynamic disabled-reason text must be specific.

---

# 8. Required tests

Create real executable tests. Reuse existing test infrastructure.

Minimum new tests:

- `frontend/src/components/help/tooltipRegistry.test.ts` or the repository’s equivalent frontend test path;
- `scripts/smoke_tooltip_coverage_browser.py`;
- `scripts/smoke_workspace_save_state.py`.

Each smoke script must return nonzero on failure.

## Tooltip tests

1. Registry keys are unique.
2. Every registry entry has title and body.
3. Every rendered major-surface control has a valid `data-help-id`.
4. Tooltips appear on hover.
5. Tooltips appear on keyboard focus.
6. Escape closes the tooltip.
7. Disabled controls still explain why they are unavailable.
8. Tooltips remain within viewport at left, right, top, and bottom edges.
9. Tooltips work inside a modal.
10. Tooltips work above the canvas.
11. Tooltips work in Data Workspace without creating one tooltip component per cell.
12. Every tooltip’s save scope matches actual behavior.
13. No tooltip click blocks the underlying action.
14. No drag handle loses drag behavior.
15. No browser console errors.

## Save-state tests

1. Open an existing project: no false unsaved marker.
2. Change zoom or selection: no dirty state.
3. Edit a Data Workspace cell: `UNSAVED WORKSPACE EDITS`.
4. Hovering tooltips: no dirty state.
5. Click Save Workspace Edits:
   - local save request occurs;
   - dirty clears only after confirmed success;
   - linked workbook is not written.
6. Make another edit while save is in flight:
   - prior response does not clear the newer dirty revision.
7. Local save failure:
   - dirty remains;
   - error is visible;
   - retry works.
8. Local save success with workbook pending:
   - `PROJECT SAVED · WORKBOOK SYNC PENDING`.
9. Run SAVE + WRITE EXCEL only against a cloned workbook:
   - local save runs first;
   - workbook mirror runs second;
   - success becomes `PROJECT SAVED · WORKBOOK SYNCED`.
10. Workbook write failure:
    - local saved state remains accurate;
    - workbook sync remains pending/failed.
11. Two-sided conflict:
    - conflict state remains;
    - tooltip explains it;
    - no overwrite.
12. Reload after local save:
    - saved workspace changes persist;
    - no false dirty marker.
13. `beforeunload` warns for genuine unsaved local edits only.
14. Workbook sync pending alone does not trigger unsaved-local warning.

## Full regression sequence

Run and record exact pass/fail results for:

1. Python compile.
2. Backend import.
3. Frontend TypeScript build.
4. Vite production build.
5. Full Python test suite.
6. Backend health route.
7. `/api/debug/routes`.
8. Normal Project Home startup.
9. Open the existing protected 829 project when available.
10. Local autosave and reload persistence.
11. Data Workspace save-state smoke test.
12. Tooltip browser coverage smoke test.
13. Visual Page Manager.
14. Canvas object persistence.
15. Component Library direct insert.
16. Saved legend insert.
17. Symbol Mapper basic smoke test.
18. Precision PDF crop.
19. Excel Layout existing tests.
20. SAVE + WRITE EXCEL against a cloned workbook only.
21. Workbook preservation verification.
22. PDF export smoke test.
23. Browser-level use of every new tooltip and save-state control.
24. Verify `.docs` is not staged or committed.
25. Confirm the compiled frontend bundle contains the tooltip registry and updated save labels.
26. Restart through the repository’s actual Control Center / Project Home workflow.
27. Leave the app running at `http://127.0.0.1:8766/app`.

---

# 9. Commit and push requirements

After every required test passes:

1. Review staged and unstaged diffs.
2. Confirm only directly related source, tests, documentation, and compiled assets required by the repository are included.
3. Confirm no `.docs`, customer workbook, project package, backup, export, or runtime customer data is staged.
4. Commit on the discovered current branch with:

`feat: add application-wide tooltips and clarify save state`

5. Push the discovered current branch normally. Never force push.
6. Verify the remote branch SHA equals local HEAD.
7. Record any GitHub Actions or status checks.
8. If a required test fails, diagnose and repair before pushing. Do not hide or weaken the test.

---

# 10. Required closeout report

Write:

`.docs\patch_backups\tooltip_save_ux_<timestamp>\TOOLTIP_SAVE_UX_CLOSEOUT.md`

Include:

- repository;
- branch;
- starting commit;
- final commit;
- remote SHA;
- backup path;
- exact files changed;
- exact diagnosis of `Unsaved workspace edits`;
- tooltip architecture;
- number of registry entries;
- total audited visible controls;
- covered controls;
- exemptions and justification;
- save-state transitions tested;
- browser surfaces tested;
- tests run with exact pass/fail;
- cloned workbook fixture path;
- workbook preservation results;
- anything not tested;
- confirmation no `.docs` or customer data was committed;
- app health and startup evidence;
- push evidence.

Do not describe the task as complete if any mandatory test was skipped or failed.
