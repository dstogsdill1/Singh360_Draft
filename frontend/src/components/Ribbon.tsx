import { useState, useEffect, useRef, type ReactNode } from 'react';
import type { FitMode } from './DocumentView';
import type { CanvasSelection, LineStyle } from '../model/types';
import { CONNECTOR_PRESETS } from '../model/connectorPresets';

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

interface Props {
  saveStatus: string;
  saveLabel?: string;
  hasProject: boolean;
  view: ViewControls;
  canvasEnabled: boolean;
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
    alignObjects: (d: 'left'|'center'|'right'|'top'|'middle'|'bottom'|'page-center-h'|'page-center-v') => void;
    distributeObjects: (d: 'horizontal'|'vertical') => void;
    matchObjectSize: (w: 'width'|'height'|'both') => void;
    addLegend: (presetIds?: string[]) => void;
    addBus: () => void;
  };
  onUploadFile: (file: File) => void;
  onUploadCsv: (file: File) => void;
  onInsertImage: (file: File) => void;
  onInsertPdfPage: () => void;
  onSaveNow: () => void;
  onOpenBackups: () => void;
  onExportPdf: () => void;
  onExportPackage: () => void;
  onRenumber: () => void;
  onOpenProject: () => void;
  onCleanWorkspace: () => void;
  onImportWorksheet: () => void;
  onArchiveCurrentProject: () => void;
  renumberBadge?: boolean;
  theme: 'dark' | 'light';
  onSetTheme: (t: 'dark' | 'light') => void;
  currentPaperLabel?: string;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
  onSetLineStyle: (style: LineStyle) => void;
}

type RibbonTab = 'File' | 'Home' | 'Insert' | 'Draw' | 'Text' | 'Arrange' | 'View' | 'Export';
const TABS: RibbonTab[] = ['File', 'Home', 'Insert', 'Draw', 'Text', 'Arrange', 'View', 'Export'];

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
  saveLabel,
  hasProject,
  view,
  canvasEnabled,
  activeTool,
  onSetTool,
  overlayMode,
  onToggleOverlay,
  canvas,
  onUploadFile,
  onUploadCsv,
  onInsertImage,
  onInsertPdfPage,
  onSaveNow,
  onOpenBackups,
  onExportPdf,
  onExportPackage,
  onRenumber,
  onOpenProject,
  onCleanWorkspace,
  onImportWorksheet,
  onArchiveCurrentProject,
  renumberBadge,
  theme,
  onSetTheme,
  currentPaperLabel,
  selection,
  onUpdateSelection,
  onSetLineStyle,
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

  const uploadBtn = (
    <label className="ribbon-btn file-ribbon-btn" title="Upload Workbook">
      Upload Workbook
      <input
        type="file"
        accept=".xlsx"
        title="Upload Workbook"
        onChange={(e) => e.target.files?.[0] && onUploadFile(e.target.files[0])}
      />
    </label>
  );

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
          <span className={`status-pill ${saveStatus}`}>{saveLabel ?? saveStatus}</span>
        </div>
      </div>

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
            <Group title="Workbook">{uploadBtn}</Group>
            <Group title="Data">{csvBtn}</Group>
            <Group title="Project">
              <button className="ribbon-btn" onClick={onOpenProject} title="Browse and open a saved project">Open Project</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onSaveNow} title="Save the project now">Save Now</button>
              <button className={`ribbon-btn ${renumberBadge ? 'badge-warn' : ''}`} disabled={!hasProject} onClick={onRenumber} title="Preview and apply new engineering sheet codes">
                Renumber Sheet Codes{renumberBadge ? ' ⚠' : ''}
              </button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onImportWorksheet} title="Import one or more worksheets from another Excel workbook">Import Worksheet</button>
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
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.undo} title="Undo (Ctrl+Z)">Undo</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.redo} title="Redo (Ctrl+Y)">Redo</button>
            </Group>
            <Group title="Edit">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.deleteSelected} title="Delete selected object (Del)">Delete</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.copySelected} title="Copy selected object(s) (Ctrl+C)">Copy</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.pasteCopied} title="Paste copied object(s) (Ctrl+V)">Paste</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.duplicateSelected} title="Duplicate selected object (Ctrl+D)">Duplicate</button>
            </Group>
            <Group title="Group">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.group} title="Group selected objects">Group</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.ungroup} title="Ungroup selected group">Ungroup</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.unlockAll} title="Unlock all objects on this page">Unlock All</button>
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
              <button className="ribbon-btn" disabled={!cx} onClick={onInsertPdfPage} title="Best quality: open PDF Crop, select a region, and render at 300/400/600 DPI">PDF Crop</button>
              <PlaceholderBtn label="Callout" />
            </Group>
            <Group title="Headings">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addPageTitle} title="Add a page title styled like the sheet heading (uppercase, ruled)">Page Title</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addSectionHeader} title="Add a section header">Section Header</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addNote} title="Add a small note label">Note Label</button>
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
            </>
          );
        })()}

        {tab === 'Arrange' && (
          <>
            <Group title="Order">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.bringForward} title="Bring selected object forward one step">Forward</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.sendBackward} title="Send selected object backward one step">Backward</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.bringToFront} title="Bring selected object to the front">To Front</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.sendToBack} title="Send selected object to the back">To Back</button>
            </Group>
            <Group title="Align">
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('left')} title="Align left edges">⊣ Left</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('center')} title="Align horizontal centers">⊟ H Center</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('right')} title="Align right edges">⊢ Right</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('top')} title="Align top edges">⊤ Top</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('middle')} title="Align vertical middles">⊞ V Middle</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('bottom')} title="Align bottom edges">⊥ Bottom</button>
            </Group>
            <Group title="Page Center">
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('page-center-h')} title="Center on page horizontally">⇔ Horiz</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.alignObjects('page-center-v')} title="Center on page vertically">⇕ Vert</button>
            </Group>
            <Group title="Distribute">
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.distributeObjects('horizontal')} title="Distribute objects horizontally (need 3+)">↔ Horiz</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.distributeObjects('vertical')} title="Distribute objects vertically (need 3+)">↕ Vert</button>
            </Group>
            <Group title="Match Size">
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.matchObjectSize('width')} title="Match width to the first selected object">= Width</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.matchObjectSize('height')} title="Match height to the first selected object">= Height</button>
              <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.matchObjectSize('both')} title="Match both width and height to the first selected object">= Both</button>
            </Group>
          </>
        )}

        {tab === 'Draw' && (() => {
          const ln = selection?.isConnector ?? false;
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
                <button className="ribbon-btn" disabled={!cx} onClick={canvas.addBus} title="Bus / Harness (B): create several parallel labeled wires at once.">Bus / Harness</button>
              </Group>
              <Group title="Line Color">
                <select className="ribbon-select" disabled={!ln} value={typeof selection?.stroke === 'string' ? selection.stroke : '#111111'} onChange={(e) => onUpdateSelection({ stroke: e.target.value })} title={ln ? 'Stroke color of the selected line/connector' : 'Select a line or connector first'}>
                  {COLORS.map(([hex, label]) => <option key={hex} value={hex}>{label}</option>)}
                </select>
              </Group>
              <Group title="Line Width">
                <select className="ribbon-select" disabled={!ln} value={selection?.strokeWidth ?? 2} onChange={(e) => onUpdateSelection({ strokeWidth: Number(e.target.value) })} title={ln ? 'Line thickness' : 'Select a line or connector first'}>
                  {[1, 2, 3, 4, 6].map((w) => <option key={w} value={w}>{w} px</option>)}
                </select>
              </Group>
              <Group title="Line Style">
                <select className="ribbon-select" disabled={!ln} value={selection?.dash ?? 'solid'} onChange={(e) => onUpdateSelection({ dash: e.target.value })} title={ln ? 'Solid / dashed / long-dash / dotted / dash-dot' : 'Select a line or connector first'}>
                  <option value="solid">Solid</option>
                  <option value="dashed">Dashed</option>
                  <option value="long-dash">Long dash</option>
                  <option value="dotted">Dotted</option>
                  <option value="dash-dot">Dash-dot</option>
                </select>
                <button className={`ribbon-btn ${selection?.arrowStart ? 'active' : ''}`} disabled={!ln} onClick={() => onUpdateSelection({ arrowStart: !selection?.arrowStart })} title="Toggle arrowhead at start">Arrow Start</button>
                <button className={`ribbon-btn ${selection?.arrowEnd ? 'active' : ''}`} disabled={!ln} onClick={() => onUpdateSelection({ arrowEnd: !selection?.arrowEnd })} title="Toggle arrowhead at end">Arrow End</button>
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
                      if (ln) {
                        // A line is already selected → just recolor it and STAY in
                        // Select mode so you can click preset after preset without
                        // having to Esc + re-select each time.
                        onUpdateSelection({ stroke: p.stroke, dash: p.dash, strokeWidth: p.strokeWidth, arrowEnd: p.arrowEnd ?? false });
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
                <button className="ribbon-btn" disabled={!cx} onClick={() => canvas.addLegend()} title="Insert an editable connector legend (grouped) using the presets">Insert Legend</button>
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
    </div>
  );
}
