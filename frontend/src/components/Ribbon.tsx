import { useState, useEffect, useRef, type ReactNode } from 'react';
import type { FitMode } from './DocumentView';
import type { CanvasSelection, LineStyle, SymbolLegendInsertConfig } from '../model/types';
import { CONNECTOR_PRESETS } from '../model/connectorPresets';
import type { DirtyDomain, SaveState } from '../model/saveState';
import SaveStateIndicator from './SaveStateIndicator';

export type PageReviewFilter = 'all' | 'included' | 'excluded';

export interface ViewControls {
  fitMode: FitMode;
  showGrid: boolean;
  snap: boolean;
  zoomPct: number;
  setFitMode: (m: FitMode) => void;
  setActual: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  toggleGrid: () => void;
  toggleSnap: () => void;
}

import TextBoxFormatControls from './TextBoxFormatControls';

interface Props {
  saveStatus: SaveState;
  savedAt?: string;
  dirtyDomains: DirtyDomain[];
  saveError?: string;
  saveStatusLabel?: string;
  onRetrySave: () => void;
  hasProject: boolean;
  view: ViewControls;
  canvasEnabled: boolean;
  viewMode: import('../model/types').ViewMode;
  sourceCanUndo?: boolean;
  sourceCanRedo?: boolean;
  activeTool: string;
  onSetTool: (tool: string) => void;
  overlayMode: boolean;
  onToggleOverlay: () => void;
  canvas: {
    addText: () => void;
    addRect: () => void;
    addCircle: () => void;
    addLine: () => void;
    addArrow: () => void;
    addPolyline: () => void;
    addElbow: () => void;
    addBracket: () => void;
    addDashedBox: () => void;
    addPageTitle: () => void;
    addSectionHeader: () => void;
    addNote: () => void;
    deleteSelected: () => void;
    copySelected: () => void;
    pasteCopied: () => void;
    duplicateSelected: () => void;
    unlockAll: () => void;
    undo: () => void;
    redo: () => void;
    group: () => void;
    ungroup: () => void;
    bringForward: () => void;
    sendBackward: () => void;
    bringToFront: () => void;
    sendToBack: () => void;
    alignObjects: (d: 'left'|'center'|'right'|'top'|'middle'|'bottom'|'page-center-h'|'page-center-v'|'page-center-both') => void;
    distributeObjects: (d: 'horizontal'|'vertical') => void;
    equalSpaceObjects: (d: 'horizontal'|'vertical') => void;
    centerInPanel: (d: 'horizontal'|'vertical'|'both') => void;
    matchObjectSize: (w: 'width'|'height'|'both') => void;
    addLegend: (presetIds?: string[]) => void;
    addSymbolLegend: (config: SymbolLegendInsertConfig) => void;
    normalizeSymbolSize: () => void;
    cropImage: () => void;
    fitImageToPage: () => void;
    fillImageToPage: () => void;
    addBus: () => void;
  };
  onUploadCsv: (file: File) => void;
  onInsertImage: (file: File) => void;
  onInsertPdfPage: () => void;
  onSaveNow: () => void;
  onProjectSettings: () => void;
  onOpenBackups: () => void;
  onExportPdf: () => void;
  onExportPackage: () => void;
  onRenumber: () => void;
  onOpenProject: () => void;
  onOpenHome: () => void;
  onCleanWorkspace: () => void;
  onImportWorksheet: () => void;
  canSavePageTemplate: boolean;
  onSavePageTemplate: () => void;
  onInsertPageTemplate: () => void;
  onManagePageTemplates: () => void;
  onInsertSymbolLegend: () => void;
  onOpenSymbolMapper: () => void;
  onSaveSelectionAssembly: () => void;
  onArchiveCurrentProject: () => void;
  renumberBadge?: boolean;
  theme: 'dark' | 'light';
  onSetTheme: (t: 'dark' | 'light') => void;
  currentPaperLabel?: string;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
  onSetLineStyle: (style: LineStyle) => void;
  pageFilter: PageReviewFilter;
  onSetPageFilter: (filter: PageReviewFilter) => void;
}

type RibbonTab = 'File' | 'Home' | 'Insert' | 'Symbols' | 'Draw' | 'Text' | 'Arrange' | 'View' | 'Export';
const TABS: RibbonTab[] = ['File', 'Home', 'Insert', 'Symbols', 'Draw', 'Text', 'Arrange', 'View', 'Export'];

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="ribbon-group">
      <div className="ribbon-group-btns">{children}</div>
      <div className="ribbon-group-title">{title}</div>
    </div>
  );
}

function PlaceholderBtn({ label }: { label: string }) {
  return (
    <button className="ribbon-btn" disabled title="Coming soon">
      {label}
    </button>
  );
}

export default function Ribbon({
  saveStatus,
  savedAt,
  dirtyDomains,
  saveError,
  saveStatusLabel,
  onRetrySave,
  hasProject,
  view,
  canvasEnabled,
  viewMode,
  sourceCanUndo,
  sourceCanRedo,
  activeTool,
  onSetTool,
  overlayMode,
  onToggleOverlay,
  canvas,
  onUploadCsv,
  onInsertImage,
  onInsertPdfPage,
  onSaveNow,
  onProjectSettings,
  onOpenBackups,
  onExportPdf,
  onExportPackage,
  onRenumber,
  onOpenProject,
  onOpenHome,
  onCleanWorkspace,
  onImportWorksheet,
  canSavePageTemplate,
  onSavePageTemplate,
  onInsertPageTemplate,
  onManagePageTemplates,
  onInsertSymbolLegend,
  onOpenSymbolMapper,
  onSaveSelectionAssembly,
  onArchiveCurrentProject,
  renumberBadge,
  theme,
  onSetTheme,
  currentPaperLabel,
  selection,
  onUpdateSelection,
  onSetLineStyle,
  pageFilter,
  onSetPageFilter,
}: Props) {
  const [tab, setTab] = useState<RibbonTab>('File');

  // Auto-switch to the relevant tab when an object is freshly selected, so the
  // right controls are visible without hunting. Only switches on a *change* of
  // selection kind (text ↔ line ↔ other), never fighting a manual tab change.
  const prevKind = useRef<string>('');
  useEffect(() => {
    const kind = selection?.isText ? 'text' : selection?.isConnector ? 'line' : selection ? 'obj' : 'none';
    if (kind !== prevKind.current) {
      prevKind.current = kind;
      if (kind === 'text') setTab('Text');
      else if (kind === 'line') setTab('Draw');
    }
  }, [selection]);
  const cx = canvasEnabled;
  const sourceMode = viewMode === 'source';
  // Canvas edit/order commands must never stay active while Source view is
  // showing the worksheet editor. Source mode keeps its own Undo/Redo only.
  const historyEnabled = cx;
  const hasSelection = cx && !!selection;
  const undoEnabled = sourceMode ? !!sourceCanUndo : cx;
  const redoEnabled = sourceMode ? !!sourceCanRedo : cx;

  const csvBtn = (
    <label className={`ribbon-btn file-ribbon-btn ${hasProject ? '' : 'disabled'}`} title="Attach CSV">
      Attach CSV
      <input
        type="file"
        accept=".csv"
        title="Attach CSV"
        disabled={!hasProject}
        onChange={(e) => e.target.files?.[0] && onUploadCsv(e.target.files[0])}
      />
    </label>
  );

  return (
    <div className="ribbon">
      <div className="ribbon-appbar">
        <div className="toolbar-brand">
          <span className="brand-main">Singh360 Draft</span>
          <span className="brand-sub">Drawing Package Editor</span>
        </div>
        <div className="ribbon-appbar-right">
          <button type="button" className="ribbon-btn ribbon-home-btn" onClick={onOpenHome}>Project Home</button>
          <button type="button" className="ribbon-btn" disabled={!hasProject} onClick={onProjectSettings}>Project Settings</button>
          <button type="button" className="ribbon-btn" disabled={!hasProject} onClick={onInsertPdfPage}>Add / Import Page</button>
          <button type="button" className="ribbon-btn ribbon-primary-save" disabled={!hasProject || saveStatus === 'savingLocal'} onClick={onSaveNow}>Save Project</button>
          <button type="button" className="ribbon-btn" disabled={!undoEnabled} onClick={canvas.undo}>Undo</button>
          <button type="button" className="ribbon-btn" disabled={!redoEnabled} onClick={canvas.redo}>Redo</button>
          <button type="button" className="ribbon-btn" disabled={!hasProject} onClick={onExportPdf}>Export PDF</button>
          <button type="button" className="ribbon-btn" disabled={!hasProject} onClick={onOpenBackups}>Backups / Recover</button>
          <SaveStateIndicator
            state={saveStatus}
            lastLocalSave={savedAt}
            dirtyDomains={dirtyDomains}
            error={saveError}
            onRetry={onRetrySave}
            labelOverride={saveStatusLabel}
          />
        </div>
      </div>

      <details className="ribbon-advanced">
        <summary>Advanced Tools</summary>
      <div className="ribbon-tabs">
        {TABS.map((t) => (
          <button key={t} className={`ribbon-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      <div className="ribbon-groups">
        {tab === 'File' && (
          <>
            <Group title="Import">{csvBtn}</Group>
            <Group title="Project">
              <button className="ribbon-btn" onClick={onOpenProject} title="Browse and open a saved project">Open Project</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onSaveNow} title="Save the current standalone project">Save Project</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onInsertPdfPage} title="Create or import a drawing page">Add / Import Page</button>
              <button className={`ribbon-btn ${renumberBadge ? 'badge-warn' : ''}`} disabled={!hasProject} onClick={onRenumber} title="Preview and apply new engineering sheet codes">
                Renumber Sheet Codes{renumberBadge ? ' ⚠' : ''}
              </button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onImportWorksheet} title="Copy one Excel worksheet into this project as editable table data">Import Excel Table</button>
            </Group>
            <Group title="Templates">
              <button className="ribbon-btn" disabled={!hasProject || !canSavePageTemplate} onClick={onSavePageTemplate} title="Save the active page layout as a reusable template">Save Page as Template</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onInsertPageTemplate} title="Insert a saved page template">Insert Page Template</button>
              <button className="ribbon-btn" onClick={onManagePageTemplates} title="Rename or delete saved page templates">Manage Page Templates</button>
            </Group>
            <Group title="Maintenance">
              <button className="ribbon-btn" onClick={onCleanWorkspace} title="Archive old projects/exports to start fresh (never deletes; library preserved)">Clean Workspace</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onOpenBackups} title="View server backup snapshots and recover unsaved drawing changes">Backups / Recover</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onArchiveCurrentProject} title="Archive the currently open project and return to the landing screen">Archive Project</button>
            </Group>
            <Group title="Output">
              <button className="ribbon-btn" disabled={!hasProject} onClick={onExportPdf} title="Choose paper size and export a PDF">Export PDF</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onExportPackage} title="Export a ZIP with project.json, manifest, sources, assets and exports">Export Package</button>
            </Group>
          </>
        )}

        {tab === 'Home' && (
          <>
            <Group title="Tools">
              <button className={`ribbon-btn ${activeTool === 'select' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('select')} title="Select and move overlay objects">Select</button>
              <button className={`ribbon-btn ${overlayMode ? 'active' : ''}`} disabled={!cx} onClick={onToggleOverlay} title="Toggle overlay edit mode: edit pasted images, shapes and annotations on top of the page">
                {overlayMode ? 'Overlay: On' : 'Edit Overlay'}
              </button>
            </Group>
            <Group title="History">
              <button className="ribbon-btn" disabled={!undoEnabled} onClick={canvas.undo} title="Undo (Ctrl+Z)">Undo</button>
              <button className="ribbon-btn" disabled={!redoEnabled} onClick={canvas.redo} title="Redo (Ctrl+Y)">Redo</button>
            </Group>
            <Group title="Edit">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.deleteSelected} title="Delete selected object (Del)">Delete</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.copySelected} title="Copy selected object(s) (Ctrl+C)">Copy</button>
              <button className="ribbon-btn" disabled={!historyEnabled} onClick={canvas.pasteCopied} title="Paste copied object(s) (Ctrl+V)">Paste</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.duplicateSelected} title="Duplicate selected object (Ctrl+D)">Duplicate</button>
            </Group>
            <Group title="Group">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.group} title="Group selected objects">Group</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.ungroup} title="Ungroup or explode the selected group into editable parts">Ungroup</button>
              <button className="ribbon-btn" disabled={!cx} data-help-id="assembly.saveSelection" onClick={onSaveSelectionAssembly}>Save Selection as Assembly</button>
              <button className="ribbon-btn" disabled={!historyEnabled} onClick={canvas.unlockAll} title="Unlock all objects on this page">Unlock All</button>
            </Group>
          </>
        )}

        {tab === 'Insert' && (
          <>
            <Group title="Basic">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addText} title="Add a text box to the overlay">Text</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addRect} title="Add a rectangle to the overlay">Rectangle</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addCircle} title="Add a circle to the overlay">Circle</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addLine} title="Add a line to the overlay">Line</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addArrow} title="Add an arrow to the overlay">Arrow</button>
            </Group>
            <Group title="Objects">
              <label className={`ribbon-btn file-ribbon-btn ${cx ? '' : 'disabled'}`} title="Insert an image (PNG/JPG/WEBP/SVG) on the active page at full resolution">
                Image
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  title="Insert Image"
                  disabled={!cx}
                  onChange={(e) => { if (e.target.files?.[0]) { onInsertImage(e.target.files[0]); e.currentTarget.value = ''; } }}
                />
              </label>
              <button className="ribbon-btn" disabled={!cx} onClick={onInsertPdfPage} title="Best quality: open PDF Crop, select a region, and render at 300/400/600 DPI">PDF Page / Crop</button>
              <PlaceholderBtn label="Callout" />
            </Group>
            <Group title="Headings">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addPageTitle} title="Add a page title styled like the sheet heading (uppercase, ruled)">Page Title</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addSectionHeader} title="Add a section header">Section Header</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addNote} title="Add a small note label">Note Label</button>
            </Group>
            <Group title="Legend">
              <button className="ribbon-btn" disabled={!cx} onClick={onInsertSymbolLegend} title="Insert an editable symbol legend from the component library">Symbol Legend</button>
            </Group>
          </>
        )}


        {tab === 'Symbols' && (
          <>
            <Group title="Symbol Mapping">
              <button
                className="ribbon-btn"
                disabled={!hasProject}
                onClick={onOpenSymbolMapper}
                title="Upload one PDF, choose symbols and ready-made colors, then run the automatic mapper"
              >
                Open Symbol Mapper
              </button>
            </Group>
          </>
        )}

        {tab === 'Text' && (() => {
          const t = selection?.isText ?? false;
          const fs = selection?.fontSize ?? 20;
          const col = typeof selection?.fill === 'string' && selection.fill.startsWith('#') ? selection.fill : '#111111';
          return (
            <>
              <Group title="Font">
                <button className={`ribbon-btn ${selection?.bold ? 'active' : ''}`} disabled={!t} onClick={() => onUpdateSelection({ bold: !selection?.bold })} title="Bold"><b>B</b></button>
                <button className={`ribbon-btn ${selection?.italic ? 'active' : ''}`} disabled={!t} onClick={() => onUpdateSelection({ italic: !selection?.italic })} title="Italic"><i>I</i></button>
                <button className={`ribbon-btn ${selection?.underline ? 'active' : ''}`} disabled={!t} onClick={() => onUpdateSelection({ underline: !selection?.underline })} title="Underline"><u>U</u></button>
              </Group>
              <Group title="Size">
                <button className="ribbon-btn" disabled={!t} onClick={() => onUpdateSelection({ fontSize: Math.max(6, fs - 2) })} title="Decrease font size">A−</button>
                <span className="ribbon-size">{t ? fs : '—'}</span>
                <button className="ribbon-btn" disabled={!t} onClick={() => onUpdateSelection({ fontSize: fs + 2 })} title="Increase font size">A+</button>
              </Group>
              <Group title="Align">
                <button className={`ribbon-btn ${selection?.textAlign === 'left' ? 'active' : ''}`} disabled={!t} onClick={() => onUpdateSelection({ textAlign: 'left' })} title="Align left">L</button>
                <button className={`ribbon-btn ${selection?.textAlign === 'center' ? 'active' : ''}`} disabled={!t} onClick={() => onUpdateSelection({ textAlign: 'center' })} title="Align center">C</button>
                <button className={`ribbon-btn ${selection?.textAlign === 'right' ? 'active' : ''}`} disabled={!t} onClick={() => onUpdateSelection({ textAlign: 'right' })} title="Align right">R</button>
              </Group>
              <Group title="Color">
                <label className="ribbon-color" title="Text color">
                  <input type="color" disabled={!t} value={col} onChange={(e) => onUpdateSelection({ fill: e.target.value })} />
                  Color
                </label>
                <button className="ribbon-btn" disabled={!t} onClick={() => onUpdateSelection({ bold: false, italic: false, underline: false })} title="Clear formatting">Clear</button>
              </Group>
                          <TextBoxFormatControls
                selection={selection}
                onChange={onUpdateSelection}
              />
</>
          );
        })()}

        {tab === 'Arrange' && (
          <>
            <Group title="Order">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.bringForward} title="Bring selected object forward one step">Forward</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.sendBackward} title="Send selected object backward one step">Backward</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.bringToFront} title="Bring selected object to the front">To Front</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.sendToBack} title="Send selected object to the back">To Back</button>
            </Group>
            <Group title="Align">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('left')} title="Align left edges">⊣ Left</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('center')} title="Align horizontal centers">⊟ H Center</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('right')} title="Align right edges">⊢ Right</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('top')} title="Align top edges">⊤ Top</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('middle')} title="Align vertical middles">⊞ V Middle</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('bottom')} title="Align bottom edges">⊥ Bottom</button>
            </Group>
            <Group title="Page Center">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('page-center-h')} title="Center on page horizontally">⇔ Horiz</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('page-center-v')} title="Center on page vertically">⇕ Vert</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.alignObjects('page-center-both')} title="Center the completed selection on the page">◎ Both</button>
            </Group>
            <Group title="Panel Center">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.centerInPanel('horizontal')} title="Center the selection horizontally inside the nearest selected or containing panel">⇔ Panel</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.centerInPanel('vertical')} title="Center the selection vertically inside the nearest selected or containing panel">⇕ Panel</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.centerInPanel('both')} title="Center the selection in the editable body of the nearest panel">◎ Panel</button>
            </Group>
            <Group title="Distribute">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.distributeObjects('horizontal')} title="Distribute objects horizontally (need 3+)">↔ Horiz</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.distributeObjects('vertical')} title="Distribute objects vertically (need 3+)">↕ Vert</button>
            </Group>
            <Group title="Equal Spacing">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.equalSpaceObjects('horizontal')} title="Make horizontal edge gaps equal while keeping the outer objects fixed (need 3+)">= H Gaps</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.equalSpaceObjects('vertical')} title="Make vertical edge gaps equal while keeping the outer objects fixed (need 3+)">= V Gaps</button>
            </Group>
            <Group title="Match Size">
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.matchObjectSize('width')} title="Match width to the first selected object">= Width</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.matchObjectSize('height')} title="Match height to the first selected object">= Height</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={() => canvas.matchObjectSize('both')} title="Match both width and height to the first selected object">= Both</button>
              <button className="ribbon-btn" disabled={!hasSelection} onClick={canvas.normalizeSymbolSize} title="Resize selected symbols to standard marker size">Normalize Symbol Size</button>
            </Group>
            <Group title="Image">
              <button className="ribbon-btn" disabled={!selection?.isImage} onClick={canvas.cropImage} title="Crop the selected image and optionally fit or fill the drawing area">Crop / Fit</button>
              <button className="ribbon-btn" disabled={!selection?.isImage} onClick={canvas.fitImageToPage} title="Fit the selected image crop inside the drawing area">Fit Page</button>
              <button className="ribbon-btn" disabled={!selection?.isImage} onClick={canvas.fillImageToPage} title="Fill the drawing area with the selected image crop">Fill Page</button>
            </Group>
          </>
        )}

        {tab === 'Draw' && (() => {
          const ln = selection?.isConnector ?? false;
          const st = !!selection && !selection.isText && !selection.isImage;
          const COLORS: Array<[string, string]> = [
            ['#111111', 'Black'], ['#888888', 'Gray'], ['#d71920', 'Red'], ['#12539b', 'Blue'],
            ['#f2c200', 'Yellow'], ['#f28c28', 'Orange'], ['#00a651', 'Green'], ['#ffffff', 'White'],
          ];
          return (
            <>
              <Group title="Place">
                <button className={`ribbon-btn ${activeTool === 'select' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('select')} title="Select / move / edit objects (Esc also returns here)">Select</button>
                <button className={`ribbon-btn ${activeTool === 'text' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('text')} title="Click-place a text box">Text</button>
                <button className={`ribbon-btn ${activeTool === 'rectangle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('rectangle')} title="Click-place a rectangle">Rectangle</button>
                <button className={`ribbon-btn ${activeTool === 'circle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('circle')} title="Click-place a circle">Circle</button>
                <button className={`ribbon-btn ${activeTool === 'line' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('line')} title="Line (L): two clicks — start point, then end point.">Line</button>
                <button className={`ribbon-btn ${activeTool === 'arrow' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('arrow')} title="Two clicks like Line, with an arrowhead on the end">Arrow</button>
                <button className={`ribbon-btn ${activeTool === 'polyline' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('polyline')} title="Multi-Point Line (P): click each point, double-click or Enter to finish, Esc to cancel.">Multi-Point Line</button>
                <button className={`ribbon-btn ${activeTool === 'elbow' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('elbow')} title="Elbow (E): orthogonal square-cornered routing. Click each bend, double-click or Enter to finish.">Elbow</button>
                <button className="ribbon-btn" disabled={!cx} onClick={canvas.addBracket} title="Insert a yellow group-bracket connector like HVAC/controls callouts">Bracket</button>
                <button className="ribbon-btn" disabled={!cx} onClick={canvas.addBus} title="Bus / Harness (B): create several parallel labeled wires at once.">Bus / Harness</button>
                <button className="ribbon-btn" disabled={!cx} onClick={canvas.addDashedBox} title="Insert a dashed boundary box for grouped devices/areas">Dashed Box</button>
              </Group>
              <Group title="Line Color">
                <select className="ribbon-select" disabled={!st} value={typeof selection?.stroke === 'string' ? selection.stroke : '#111111'} onChange={(e) => onUpdateSelection({ stroke: e.target.value })} title={st ? 'Stroke color of the selected line/boundary' : 'Select a line, bracket, or dashed box first'}>
                  {COLORS.map(([hex, label]) => <option key={hex} value={hex}>{label}</option>)}
                </select>
              </Group>
              <Group title="Line Width">
                <select className="ribbon-select" disabled={!st} value={selection?.strokeWidth ?? 2} onChange={(e) => onUpdateSelection({ strokeWidth: Number(e.target.value) })} title={st ? 'Line / boundary thickness' : 'Select a line, bracket, or dashed box first'}>
                  {[1, 2, 3, 4, 6].map((w) => <option key={w} value={w}>{w} px</option>)}
                </select>
              </Group>
              <Group title="Line Style">
                <select className="ribbon-select" disabled={!st} value={selection?.dash ?? 'solid'} onChange={(e) => onUpdateSelection({ dash: e.target.value })} title={st ? 'Solid / dashed / long-dash / dotted / dash-dot' : 'Select a line, bracket, or dashed box first'}>
                  <option value="solid">Solid</option>
                  <option value="dashed">Dashed</option>
                  <option value="long-dash">Long dash</option>
                  <option value="dotted">Dotted</option>
                  <option value="dash-dot">Dash-dot</option>
                </select>
                <button className={`ribbon-btn ${selection?.arrowStart ? 'active' : ''}`} disabled={!ln} onClick={() => onUpdateSelection({ arrowStart: !selection?.arrowStart })} title="Toggle arrowhead at start">Arrow Start</button>
                <button className={`ribbon-btn ${selection?.arrowEnd ? 'active' : ''}`} disabled={!ln} onClick={() => onUpdateSelection({ arrowEnd: !selection?.arrowEnd })} title="Toggle arrowhead at end">Arrow End</button>
              </Group>
              <Group title="Edit">
                <button className="ribbon-btn" disabled={!selection} onClick={() => onUpdateSelection({ angle: (selection?.angle ?? 0) - 90 })} title="Rotate selected object -90°">↺ -90°</button>
                <button className="ribbon-btn" disabled={!selection} onClick={() => onUpdateSelection({ angle: (selection?.angle ?? 0) + 90 })} title="Rotate selected object +90°">↻ +90°</button>
              </Group>
              <Group title="Presets">
                {CONNECTOR_PRESETS.map((p) => (
                  <button
                    key={p.id}
                    className="ribbon-btn"
                    disabled={!cx}
                    onClick={() => {
                      // Remember this style for the NEXT new line.
                      onSetLineStyle({ stroke: p.stroke, dash: p.dash, strokeWidth: p.strokeWidth, arrowStart: false, arrowEnd: p.arrowEnd ?? false });
                      if (st) {
                        // A line is already selected → just recolor it and STAY in
                        // Select mode so you can click preset after preset without
                        // having to Esc + re-select each time.
                        onUpdateSelection({ stroke: p.stroke, dash: p.dash, strokeWidth: p.strokeWidth, arrowEnd: ln ? (p.arrowEnd ?? false) : undefined });
                      } else {
                        // Nothing selected → arm the Line tool pre-styled to draw one.
                        onSetTool('line');
                      }
                    }}
                    title={`${p.label}: recolor the selected line, or (nothing selected) start a new ${p.label} line`}
                  >
                    {p.label}
                  </button>
                ))}
              </Group>
              <Group title="Legend">
                <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.addLegend()} title="Insert an editable connector legend (grouped) using the presets">Connector Legend</button>
                <button className="ribbon-btn" disabled={!cx} onClick={onInsertSymbolLegend} title="Insert an editable symbol legend from the component library">Symbol Legend</button>
              </Group>
            </>
          );
        })()}

        {tab === 'View' && (
          <>
            <Group title="Fit">
              <button className={`ribbon-btn ${view.fitMode === 'page' ? 'active' : ''}`} disabled={!hasProject} onClick={() => view.setFitMode('page')}>Fit Page</button>
              <button className={`ribbon-btn ${view.fitMode === 'width' ? 'active' : ''}`} disabled={!hasProject} onClick={() => view.setFitMode('width')}>Fit Width</button>
              <button className={`ribbon-btn ${view.fitMode === 'actual' ? 'active' : ''}`} disabled={!hasProject} onClick={view.setActual}>100%</button>
            </Group>
            <Group title="Zoom">
              <button className="ribbon-btn" disabled={!hasProject} onClick={view.zoomOut}>−</button>
              <button className="ribbon-btn" disabled title="Current zoom">{view.zoomPct}%</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={view.zoomIn}>+</button>
            </Group>
            {/* S360 RAPID PAGE REVIEW V35 */}
            <Group title="Page Filter">
              <button className={`ribbon-btn ${pageFilter === 'all' ? 'active' : ''}`} disabled={!hasProject} onClick={() => onSetPageFilter('all')}>All Pages</button>
              <button className={`ribbon-btn ${pageFilter === 'included' ? 'active' : ''}`} disabled={!hasProject} onClick={() => onSetPageFilter('included')}>Included Only</button>
              <button className={`ribbon-btn ${pageFilter === 'excluded' ? 'active' : ''}`} disabled={!hasProject} onClick={() => onSetPageFilter('excluded')}>Not Included</button>
            </Group>
            <Group title="Grid">
              <button className={`ribbon-btn ${view.showGrid ? 'active' : ''}`} disabled={!hasProject} onClick={view.toggleGrid}>Show Grid</button>
              <button className={`ribbon-btn ${view.snap ? 'active' : ''}`} disabled={!hasProject} onClick={view.toggleSnap}>Snap</button>
            </Group>
            <Group title="Theme">
              <button className={`ribbon-btn ${theme === 'dark' ? 'active' : ''}`} onClick={() => onSetTheme('dark')} title="Dark workspace (default)">Dark</button>
              <button className={`ribbon-btn ${theme === 'light' ? 'active' : ''}`} onClick={() => onSetTheme('light')} title="Light workspace for daylight / screenshots">Light</button>
            </Group>
          </>
        )}

        {tab === 'Export' && (
          <>
            <Group title="PDF">
              <button className="ribbon-btn" disabled={!hasProject} onClick={onExportPdf} title="Choose paper size and export a PDF">Export PDF</button>
              <span className="ribbon-readout" title="Current export paper size">{currentPaperLabel || 'ANSI B / 11 x 17'}</span>
            </Group>
            <Group title="Package">
              <PlaceholderBtn label="Package Export" />
            </Group>
          </>
        )}
      </div>
      </details>
    </div>
  );
}
