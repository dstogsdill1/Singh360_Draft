import { useState } from 'react';
import type { CanvasSelection, PageModel } from '../model/types';
import { PAGE_TEMPLATES, applyTemplate, templateForPage, type PageTemplate } from '../model/pageTemplates';

interface Props {
  page: PageModel;
  onChange: (next: PageModel) => void;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
  projectDisplayName?: string;
  projectFolder?: string;
  onRenameProject?: (name: string) => void;
  overflowWarning?: boolean;
  onMergeIntoPrevious?: () => void;
  onMakeIndependent?: () => void;
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
  onMergeIntoPrevious,
  onMakeIndependent,
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
          {projectFolder && (
            <div className="field">
              <label>Assets Folder</label>
              <div className="props-path" title={`${projectFolder}\\assets\\images`}>{projectFolder}\assets\images</div>
            </div>
          )}
          {projectFolder && (
            <div className="field">
              <label>Screenshots / Pasted</label>
              <div className="props-path" title={`${projectFolder}\\assets\\images`}>{projectFolder}\assets\images</div>
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

      {page.continuationOf && (
        <div className="props-group props-warning">
          <h3>↳ Continuation Page</h3>
          <p className="props-note">This sheet is a continuation of a previous page.</p>
          {onMergeIntoPrevious && (
            <button className="props-btn" onClick={onMergeIntoPrevious} title="Move this page's blocks back into the previous page and remove this continuation">
              Merge Into Previous
            </button>
          )}
          {onMakeIndependent && (
            <button className="props-btn" onClick={onMakeIndependent} title="Break the link to the base page so this page becomes a standalone sheet">
              Make Independent Sheet
            </button>
          )}
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
          <label htmlFor="page-type">Page Template</label>
          <select
            id="page-type"
            value={templateForPage(page)}
            onChange={(e) => onChange(applyTemplate(page, e.target.value as PageTemplate))}
          >
            {PAGE_TEMPLATES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
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
              <input id="sel-type" title="What kind of object is selected" value={selection.isConnector ? 'Line / Connector' : selection.isText ? 'Text' : selection.isImage ? 'Image' : selection.type} readOnly />
            </div>
            {selection.name !== undefined && (
              <div className="field">
                <label htmlFor="sel-name">Object Name</label>
                <input id="sel-name" type="text" title="A label for this object (does not appear on the sheet)" value={selection.name} onChange={(e) => onUpdateSelection({ name: e.target.value })} />
              </div>
            )}
            <div className="field-row">
              <div className="field">
                <label htmlFor="sel-x" title="Horizontal position on the sheet (pixels from the left)">X Position</label>
                <input id="sel-x" type="number" value={selection.x ?? 0} onChange={(e) => onUpdateSelection({ x: Number(e.target.value) })} />
              </div>
              <div className="field">
                <label htmlFor="sel-y" title="Vertical position on the sheet (pixels from the top)">Y Position</label>
                <input id="sel-y" type="number" value={selection.y ?? 0} onChange={(e) => onUpdateSelection({ y: Number(e.target.value) })} />
              </div>
            </div>
            {!selection.isConnector && (
              <>
                <div className="field-row">
                  <div className="field">
                    <label htmlFor="sel-w" title="Object width">Width</label>
                    <input id="sel-w" type="number" value={selection.width ?? 0} onChange={(e) => onUpdateSelection({ width: Number(e.target.value) })} />
                  </div>
                  <div className="field">
                    <label htmlFor="sel-h" title="Object height">Height</label>
                    <input id="sel-h" type="number" value={selection.height ?? 0} onChange={(e) => onUpdateSelection({ height: Number(e.target.value) })} />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="sel-angle" title="Rotation in degrees">Rotation</label>
                  <input id="sel-angle" type="number" step={1} value={selection.angle ?? 0} onChange={(e) => onUpdateSelection({ angle: Number(e.target.value) })} />
                </div>
              </>
            )}
            {!selection.isConnector && !selection.isImage && (
              <div className="field">
                <label htmlFor="sel-fill" title="Inside (fill) color. Use 'transparent' for no fill.">Fill Color</label>
                <input id="sel-fill" type="text" value={selection.fill} placeholder="transparent" onChange={(e) => onUpdateSelection({ fill: e.target.value })} />
              </div>
            )}
            {!selection.isImage && (
              <div className="field">
                <label htmlFor="sel-stroke" title={selection.isConnector ? 'Line color' : 'Border / outline color'}>{selection.isConnector ? 'Line Color' : 'Stroke Color'}</label>
                <input id="sel-stroke" type="text" value={selection.stroke} placeholder="#111111" onChange={(e) => onUpdateSelection({ stroke: e.target.value })} />
              </div>
            )}
            {!selection.isImage && (
              <div className="field">
                <label htmlFor="sel-sw" title="Line / border thickness in pixels">Line Width</label>
                <input id="sel-sw" type="number" min={0} step={0.5} value={selection.strokeWidth} onChange={(e) => onUpdateSelection({ strokeWidth: Number(e.target.value) })} />
              </div>
            )}
            {selection.isConnector && (
              <>
                <div className="field">
                  <label htmlFor="sel-dash" title="Solid, dashed, dotted, or dash-dot line">Line Style</label>
                  <select id="sel-dash" value={selection.dash ?? 'solid'} onChange={(e) => onUpdateSelection({ dash: e.target.value })}>
                    <option value="solid">Solid</option>
                    <option value="dashed">Dashed</option>
                    <option value="long-dash">Long dash</option>
                    <option value="dotted">Dotted</option>
                    <option value="dash-dot">Dash-dot</option>
                  </select>
                </div>
                <div className="field">
                  <label title="Show an arrowhead at the end of the line">
                    <input type="checkbox" checked={selection.arrowEnd ?? false} onChange={(e) => onUpdateSelection({ arrowEnd: e.target.checked })} /> Arrowhead (end)
                  </label>
                </div>
              </>
            )}
            <div className="field">
              <label htmlFor="sel-opacity" title="Transparency: 1 = solid, 0 = fully transparent">Opacity</label>
              <input id="sel-opacity" type="number" min={0} max={1} step={0.05} value={selection.opacity ?? 1} onChange={(e) => onUpdateSelection({ opacity: Number(e.target.value) })} />
            </div>
            {selection.fontSize !== undefined && (
              <div className="field">
                <label htmlFor="sel-fs" title="Text size in points">Font Size</label>
                <input id="sel-fs" type="number" min={6} step={1} value={selection.fontSize} onChange={(e) => onUpdateSelection({ fontSize: Number(e.target.value) })} />
              </div>
            )}
            <div className="field">
              <label title="Prevent this object from being moved or resized by accident">
                <input type="checkbox" checked={selection.locked} onChange={(e) => onUpdateSelection({ locked: e.target.checked })} /> Lock Object
              </label>
            </div>
          </>
        )}
      </div>
    </>
  );
}
