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
  canvas: {
    addText: () => void;
    addRect: () => void;
    addLine: () => void;
    addArrow: () => void;
    deleteSelected: () => void;
    duplicateSelected: () => void;
    undo: () => void;
    redo: () => void;
  };
  onUploadFile: (file: File) => void;
  onSaveNow: () => void;
  onExportPdf: () => void;
}

type RibbonTab = 'File' | 'Home' | 'Insert' | 'Draw' | 'View' | 'Export';
const TABS: RibbonTab[] = ['File', 'Home', 'Insert', 'Draw', 'View', 'Export'];

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
  canvas,
  onUploadFile,
  onSaveNow,
  onExportPdf,
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
            <Group title="Project">
              <button className="ribbon-btn" disabled={!hasProject} onClick={onSaveNow}>Save Now</button>
            </Group>
            <Group title="Output">
              <button className="ribbon-btn" disabled={!hasProject} onClick={onExportPdf}>Export PDF</button>
            </Group>
          </>
        )}

        {tab === 'Home' && (
          <>
            <Group title="Tools">
              <button className={`ribbon-btn ${activeTool === 'select' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('select')}>Select</button>
              <button className="ribbon-btn" disabled title="Coming soon">Pan</button>
            </Group>
            <Group title="History">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.undo}>Undo</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.redo}>Redo</button>
            </Group>
            <Group title="Edit">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.deleteSelected}>Delete</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.duplicateSelected}>Duplicate</button>
            </Group>
          </>
        )}

        {tab === 'Insert' && (
          <>
            <Group title="Basic">
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addText}>Text</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addRect}>Rectangle</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addLine}>Line</button>
              <button className="ribbon-btn" disabled={!cx} onClick={canvas.addArrow}>Arrow</button>
            </Group>
            <Group title="Objects">
              <PlaceholderBtn label="Image" />
              <PlaceholderBtn label="Table" />
            </Group>
          </>
        )}

        {tab === 'Draw' && (
          <>
            <Group title="Place">
              <button className={`ribbon-btn ${activeTool === 'text' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('text')}>Text</button>
              <button className={`ribbon-btn ${activeTool === 'rectangle' ? 'active' : ''}`} disabled={!cx} onClick={() => onSetTool('rectangle')}>Rectangle</button>
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
