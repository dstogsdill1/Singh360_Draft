import { useState, type ReactNode } from 'react';
import type { FitMode } from './DocumentView';

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
  onSaveNow: () => void;
  onExportPdf: () => void;
  onExportPackage: () => void;
  onRenumber: () => void;
}

type RibbonTab = 'File' | 'Home' | 'Insert' | 'Draw' | 'Arrange' | 'View' | 'Export';
const TABS: RibbonTab[] = ['File', 'Home', 'Insert', 'Draw', 'Arrange', 'View', 'Export'];

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
  onSaveNow,
  onExportPdf,
  onExportPackage,
  onRenumber,
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
              <PlaceholderBtn label="Callout" />
              <PlaceholderBtn label="Table" />
            </Group>
          </>
        )}

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

        {tab === 'Draw' && (
          <>
            <Group title="Place">
              <button className={`ribbon-btn ${activeTool === 'text' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('text')}>Text</button>
              <button className={`ribbon-btn ${activeTool === 'rectangle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('rectangle')}>Rectangle</button>
              <button className={`ribbon-btn ${activeTool === 'circle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('circle')}>Circle</button>
              <button className={`ribbon-btn ${activeTool === 'line' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('line')}>Line</button>
              <button className={`ribbon-btn ${activeTool === 'arrow' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('arrow')}>Arrow</button>
            </Group>
            <Group title="Drawing">
              <PlaceholderBtn label="Connector" />
              <PlaceholderBtn label="Callout" />
            </Group>
          </>
        )}

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
