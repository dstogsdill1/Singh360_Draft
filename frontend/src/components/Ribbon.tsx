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

export default function Ribbon({ saveStatus, hasProject, view, onUploadFile, onSaveNow, onExportPdf }: Props) {
  const [tab, setTab] = useState<RibbonTab>('File');

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
              <PlaceholderBtn label="Select" />
              <PlaceholderBtn label="Pan" />
            </Group>
            <Group title="History">
              <PlaceholderBtn label="Undo" />
              <PlaceholderBtn label="Redo" />
            </Group>
            <Group title="Edit">
              <PlaceholderBtn label="Delete" />
              <PlaceholderBtn label="Duplicate" />
            </Group>
          </>
        )}

        {tab === 'Insert' && (
          <>
            <Group title="Basic">
              <PlaceholderBtn label="Text" />
              <PlaceholderBtn label="Rectangle" />
              <PlaceholderBtn label="Line" />
              <PlaceholderBtn label="Arrow" />
            </Group>
            <Group title="Objects">
              <PlaceholderBtn label="Image" />
              <PlaceholderBtn label="Table" />
            </Group>
          </>
        )}

        {tab === 'Draw' && (
          <Group title="Drawing">
            <PlaceholderBtn label="Connector" />
            <PlaceholderBtn label="Callout" />
            <PlaceholderBtn label="Shapes" />
          </Group>
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
