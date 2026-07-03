import { useState, type ReactNode } from 'react';
import type { FitMode } from './DocumentView';
import type { CanvasSelection } from '../model/types';

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
    addPageTitle: () => void;
    addSectionHeader: () => void;
    addNote: () => void;
    deleteSelected: () => void;
    duplicateSelected: () => void;
    undo: () => void;
    redo: () => void;
    group: () => void;
    ungroup: () => void;
    bringForward: () => void;
    sendBackward: () => void;
    bringToFront: () => void;
    sendToBack: () => void;
  };
  onUploadFile: (file: File) => void;
  onUploadCsv: (file: File) => void;
  onInsertImage: (file: File) => void;
  onSaveNow: () => void;
  onExportPdf: () => void;
  onExportPackage: () => void;
  onRenumber: () => void;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
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
  onSaveNow,
  onExportPdf,
  onExportPackage,
  onRenumber,
  selection,
  onUpdateSelection,
}: Props) {
  const [tab, setTab] = useState<RibbonTab>('File');
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
          <span className={`status-pill ${saveStatus}`}>{saveStatus}</span>
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
              <button className="ribbon-btn" disabled={!hasProject} onClick={onSaveNow} title="Save the project now">Save Now</button>
              <button className="ribbon-btn" disabled={!hasProject} onClick={onRenumber} title="Preview and apply new engineering sheet codes">Renumber Sheet Codes</button>
            </Group>
            <Group title="Output">
              <button className="ribbon-btn" disabled={!hasProject} onClick={onExportPdf} title="Export the included pages to a 17x11 PDF">Export PDF</button>
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
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.duplicateSelected} title="Duplicate selected object (Ctrl+D)">Duplicate</button>
            </Group>
            <Group title="Group">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.group} title="Group selected objects">Group</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.ungroup} title="Ungroup selected group">Ungroup</button>
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
              <PlaceholderBtn label="Callout" />
              <PlaceholderBtn label="Table" />
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
              <PlaceholderBtn label="Left" />
              <PlaceholderBtn label="Center" />
              <PlaceholderBtn label="Right" />
            </Group>
            <Group title="Distribute">
              <PlaceholderBtn label="Horizontal" />
              <PlaceholderBtn label="Vertical" />
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
                <button className={`ribbon-btn ${activeTool === 'text' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('text')} title="Click-place a text box">Text</button>
                <button className={`ribbon-btn ${activeTool === 'rectangle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('rectangle')} title="Click-place a rectangle">Rectangle</button>
                <button className={`ribbon-btn ${activeTool === 'circle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('circle')} title="Click-place a circle">Circle</button>
                <button className={`ribbon-btn ${activeTool === 'line' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('line')} title="Drag to draw a line">Line</button>
                <button className={`ribbon-btn ${activeTool === 'arrow' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('arrow')} title="Drag to draw an arrow">Arrow</button>
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
                <select className="ribbon-select" disabled={!ln} value={selection?.dash ?? 'solid'} onChange={(e) => onUpdateSelection({ dash: e.target.value })} title={ln ? 'Solid / dashed / dotted / dash-dot' : 'Select a line or connector first'}>
                  <option value="solid">Solid</option>
                  <option value="dashed">Dashed</option>
                  <option value="dotted">Dotted</option>
                  <option value="dash-dot">Dash-dot</option>
                </select>
                <button className={`ribbon-btn ${selection?.arrowEnd ? 'active' : ''}`} disabled={!ln} onClick={() => onUpdateSelection({ arrowEnd: !selection?.arrowEnd })} title="Toggle arrowhead at the end">Arrow</button>
              </Group>
              <Group title="Presets">
                <button className="ribbon-btn" disabled={!ln} onClick={() => onUpdateSelection({ stroke: '#00a651', dash: 'solid', arrowEnd: false })} title="CAT6 = green solid">CAT6</button>
                <button className="ribbon-btn" disabled={!ln} onClick={() => onUpdateSelection({ stroke: '#f28c28', dash: 'dashed', arrowEnd: false })} title="Fiber = orange dashed">Fiber</button>
                <button className="ribbon-btn" disabled={!ln} onClick={() => onUpdateSelection({ stroke: '#12539b', dash: 'dashed', arrowEnd: false })} title="BACnet = blue dashed">BACnet</button>
                <button className="ribbon-btn" disabled={!ln} onClick={() => onUpdateSelection({ stroke: '#888888', dash: 'dashed', arrowEnd: false })} title="Reference = gray dashed">Ref</button>
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
          </>
        )}

        {tab === 'Export' && (
          <>
            <Group title="PDF">
              <button className="ribbon-btn" disabled={!hasProject} onClick={onExportPdf}>Export PDF 17x11</button>
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
