import { useState } from 'react';
import type { CanvasSelection, PageModel } from '../model/types';

interface Props {
  page: PageModel;
  onChange: (next: PageModel) => void;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
  projectDisplayName?: string;
  projectFolder?: string;
  onRenameProject?: (name: string) => void;
  overflowWarning?: boolean;
}

export default function PropertiesPanel({
  page,
  onChange,
  selection,
  onUpdateSelection,
  projectDisplayName,
  projectFolder,
  onRenameProject,
  overflowWarning,
}: Props) {
  const [renameValue, setRenameValue] = useState('');
  return (
    <>
      {(projectDisplayName !== undefined || projectFolder) && (
        <div className="props-group">
          <h3>Project</h3>
          <div className="field">
            <label htmlFor="proj-name">Display Name</label>
            <input
              id="proj-name"
              value={renameValue || projectDisplayName || ''}
              onChange={(e) => setRenameValue(e.target.value)}
            />
          </div>
          {onRenameProject && (
            <button
              className="props-btn"
              disabled={!renameValue.trim() || renameValue.trim() === projectDisplayName}
              onClick={() => {
                onRenameProject(renameValue.trim());
                setRenameValue('');
              }}
            >
              Rename Project
            </button>
          )}
          {projectFolder && (
            <div className="field">
              <label>Project Folder</label>
              <div className="props-path" title={projectFolder}>{projectFolder}</div>
            </div>
          )}
        </div>
      )}

      {overflowWarning && (
        <div className="props-group props-warning">
          <h3>⚠ Layout Warning</h3>
          <p className="props-note">Content exceeds printable area. Consider recomposing, scaling, or splitting this page.</p>
        </div>
      )}

      <div className="props-group">
        <h3>Page Properties</h3>
        <div className="field">
          <label htmlFor="page-code">Sheet Code</label>
          <input id="page-code" value={page.sheetCode} onChange={(e) => onChange({ ...page, sheetCode: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="page-title">Sheet Title</label>
          <input id="page-title" value={page.sheetTitle} onChange={(e) => onChange({ ...page, sheetTitle: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="page-type">Page Type</label>
          <select id="page-type" value={page.pageType} onChange={(e) => onChange({ ...page, pageType: e.target.value as PageModel['pageType'] })}>
            <option value="data-grid">data-grid</option>
            <option value="canvas">canvas</option>
            <option value="underlay">underlay</option>
            <option value="hybrid">hybrid</option>
            <option value="cover">cover</option>
            <option value="index">index</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="page-notes">Notes</label>
          <textarea id="page-notes" value={page.notes} onChange={(e) => onChange({ ...page, notes: e.target.value })} rows={4} />
        </div>
      </div>

      <div className="props-group">
        <h3>Selection Properties</h3>
        {!selection ? (
          <p className="props-note">Select a table cell, shape, or object to edit properties.</p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="sel-type">Object Type</label>
              <input id="sel-type" title="Object type" value={selection.type} readOnly />
            </div>
            {selection.name !== undefined && (
              <div className="field">
                <label htmlFor="sel-name">Object Name</label>
                <input id="sel-name" type="text" value={selection.name} onChange={(e) => onUpdateSelection({ name: e.target.value })} />
              </div>
            )}
            <div className="field-row">
              <div className="field">
                <label htmlFor="sel-x">X</label>
                <input id="sel-x" type="number" value={selection.x ?? 0} onChange={(e) => onUpdateSelection({ x: Number(e.target.value) })} />
              </div>
              <div className="field">
                <label htmlFor="sel-y">Y</label>
                <input id="sel-y" type="number" value={selection.y ?? 0} onChange={(e) => onUpdateSelection({ y: Number(e.target.value) })} />
              </div>
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="sel-w">W</label>
                <input id="sel-w" type="number" value={selection.width ?? 0} onChange={(e) => onUpdateSelection({ width: Number(e.target.value) })} />
              </div>
              <div className="field">
                <label htmlFor="sel-h">H</label>
                <input id="sel-h" type="number" value={selection.height ?? 0} onChange={(e) => onUpdateSelection({ height: Number(e.target.value) })} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="sel-angle">Rotation</label>
              <input id="sel-angle" type="number" step={1} value={selection.angle ?? 0} onChange={(e) => onUpdateSelection({ angle: Number(e.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="sel-fill">Fill</label>
              <input id="sel-fill" type="text" value={selection.fill} placeholder="transparent" onChange={(e) => onUpdateSelection({ fill: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sel-stroke">Stroke</label>
              <input id="sel-stroke" type="text" value={selection.stroke} placeholder="#111111" onChange={(e) => onUpdateSelection({ stroke: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sel-sw">Stroke Width</label>
              <input id="sel-sw" type="number" min={0} step={0.5} value={selection.strokeWidth} onChange={(e) => onUpdateSelection({ strokeWidth: Number(e.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="sel-opacity">Opacity</label>
              <input id="sel-opacity" type="number" min={0} max={1} step={0.05} value={selection.opacity ?? 1} onChange={(e) => onUpdateSelection({ opacity: Number(e.target.value) })} />
            </div>
            {selection.fontSize !== undefined && (
              <div className="field">
                <label htmlFor="sel-fs">Font Size</label>
                <input id="sel-fs" type="number" min={6} step={1} value={selection.fontSize} onChange={(e) => onUpdateSelection({ fontSize: Number(e.target.value) })} />
              </div>
            )}
            <div className="field">
              <label>
                <input type="checkbox" checked={selection.locked} onChange={(e) => onUpdateSelection({ locked: e.target.checked })} /> Lock object
              </label>
            </div>
          </>
        )}
      </div>
    </>
  );
}
