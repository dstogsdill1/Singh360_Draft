import { useState } from 'react';
import type { CanvasSelection, PageModel } from '../model/types';
import { USER_PAGE_TEMPLATES, applyTemplate, templateForPage, type PageTemplate } from '../model/pageTemplates';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';
import { BODY_H, BODY_W } from '../model/sheetGeometry';
import { SMART_COMPONENT_LABELS } from '../model/smartComponents';

interface Props {
  page: PageModel;
  onChange: (patch: Partial<PageModel>) => void;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
  projectDisplayName?: string;
  projectFolder?: string;
  onRenameProject?: (name: string) => void;
  overflowWarning?: boolean;
  onMergeIntoPrevious?: () => void;
  onMakeIndependent?: () => void;
  onReapplyPagination?: () => void;
  onApplyExcelLayout?: (layout: 'exact_source' | 'two_columns' | 'keep_one_page') => void;
  onConnectorConvert?: (kind: 'line' | 'arrow' | 'polyline' | 'elbow') => void;
  onConnectorAddVertex?: () => void;
  onConnectorDeleteVertex?: () => void;
  onConnectorReverse?: () => void;
  onEditSmartComponent?: () => void;
  onExplodeSmartComponent?: () => void;
  onEditCallout?: () => void;
  onEditPlacedSymbol?: () => void;
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
  onReapplyPagination,
  onApplyExcelLayout,
  onConnectorConvert,
  onConnectorAddVertex,
  onConnectorDeleteVertex,
  onConnectorReverse,
  onEditSmartComponent,
  onExplodeSmartComponent,
  onEditCallout,
  onEditPlacedSymbol,
}: Props) {
  const [renameValue, setRenameValue] = useState('');
  const managedPage = isCoverPage(page) || isSheetIndexPage(page);
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

      {page.continuationOf && !managedPage && (
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
        {managedPage ? <p className="props-note">This page is maintained automatically. Update cover fields in Project Settings.</p> : null}
        {page.renderMode === 'excel_exact' && !page.continuationOf && onApplyExcelLayout && (
          <div className="field">
            <label htmlFor="excel-layout">Excel Layout</label>
            <select
              id="excel-layout"
              aria-label="Excel Layout"
              value={page.layoutOverride === 'two_columns' || page.layoutOverride === 'keep_one_page' ? page.layoutOverride : 'exact_source'}
              onChange={(event) => onApplyExcelLayout(event.target.value as 'exact_source' | 'two_columns' | 'keep_one_page')}
            >
              <option value="exact_source">Exact Source / Auto</option>
              <option value="two_columns">Two Columns</option>
              <option value="keep_one_page">Keep on One Page</option>
            </select>
            <p className="props-note">Exact Source preserves Excel geometry. Two Columns and Keep on One Page are explicit overrides.</p>
          </div>
        )}
        <div className="field">
          <label htmlFor="page-code">Sheet Code</label>
          <input id="page-code" value={page.sheetCode} disabled={managedPage} onChange={(e) => onChange({ sheetCode: e.target.value, displaySheetCode: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="page-title">Sheet Title</label>
          <input id="page-title" value={page.sheetTitle} disabled={managedPage} onChange={(e) => onChange({ sheetTitle: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="page-type">Page Template</label>
          <select
            id="page-type"
            value={templateForPage(page)}
            disabled={managedPage}
            onChange={(e) => {
              const applied = applyTemplate(page, e.target.value as PageTemplate);
              onChange({ template: applied.template, pageType: applied.pageType });
            }}
          >
            {(managedPage ? [templateForPage(page)] : USER_PAGE_TEMPLATES).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        {page.layoutProfile === 'network_48_port' && (
          <label className="lib-showretired" title="Show Terminated By only when there is enough room on the network table">
            <input
              type="checkbox"
              checked={!!page.showTerminatedBy}
              onChange={(e) => onChange({ showTerminatedBy: e.target.checked })}
            />
            {' '}Show Terminated By column
          </label>
        )}
        <div className="field">
          <label htmlFor="page-notes">Notes</label>
          <textarea id="page-notes" value={page.notes} disabled={managedPage} onChange={(e) => onChange({ notes: e.target.value })} rows={4} />
        </div>
      </div>

      {page.renderMode === 'excel_exact' && !page.continuationOf && (
        <div className="props-group">
          <h3>Excel Range / Continuation</h3>
          <div className="field">
            <label htmlFor="page-src-range">Source Range</label>
            <input
              id="page-src-range"
              value={page.sourceRange || ''}
              onChange={(e) => onChange({ sourceRange: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="page-print-area">Print Area</label>
            <input
              id="page-print-area"
              value={page.printArea || ''}
              placeholder="e.g. A1:K45"
              onChange={(e) => onChange({ printArea: e.target.value || null })}
            />
          </div>
          <div className="field">
            <label htmlFor="page-split-mode">Split Mode</label>
            <select
              id="page-split-mode"
              value={page.splitMode || 'auto_rows'}
              onChange={(e) => onChange({ splitMode: e.target.value })}
            >
              <option value="none">None (scale/warn only)</option>
              <option value="auto_rows">Auto — split by rows</option>
              <option value="manual_ranges">Manual ranges</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="page-repeat-rows">Repeat Header Rows (0-based, comma)</label>
            <input
              id="page-repeat-rows"
              value={(page.repeatRows ?? []).join(', ')}
              onChange={(e) => {
                const rows = e.target.value
                  .split(',')
                  .map((x) => x.trim())
                  .filter(Boolean)
                  .map((x) => Number(x))
                  .filter((n) => Number.isFinite(n) && n >= 0);
                onChange({ repeatRows: rows });
              }}
            />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="page-min-scale">Min Scale</label>
              <input
                id="page-min-scale"
                type="number"
                min={0.2}
                max={1}
                step={0.05}
                value={page.minScale ?? 0.5}
                onChange={(e) => onChange({ minScale: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label htmlFor="page-allow-cont" title="Allow automatic continuation pages when the range overflows">
                <input
                  id="page-allow-cont"
                  type="checkbox"
                  checked={page.allowContinuation !== false}
                  onChange={(e) => onChange({ allowContinuation: e.target.checked })}
                />
                {' '}Allow continuation
              </label>
            </div>
          </div>
          {onReapplyPagination && (
            <button
              type="button"
              className="props-btn"
              title="Re-run row-splitting with the settings above"
              onClick={onReapplyPagination}
            >
              Re-apply Pagination
            </button>
          )}
        </div>
      )}

      <div className="props-group">
        <h3>Selection Properties</h3>
        {!selection ? (
          <p className="props-note">Select a table cell, shape, or object to edit properties.</p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="sel-type">Object Type</label>
              <input id="sel-type" title="What kind of object is selected" value={selection.calloutConfig ? 'Editable Callout Set' : selection.smartComponentType ? `Smart ${SMART_COMPONENT_LABELS[selection.smartComponentType]}` : selection.isPlacedSymbol ? 'Placed Symbol / Component' : selection.isConnector ? (selection.connectorKind === 'elbow' ? 'Elbow Connector' : selection.connectorKind === 'polyline' ? 'Polyline' : selection.connectorKind === 'arrow' ? 'Arrow' : 'Line') : selection.isText ? 'Text' : selection.isImage ? 'Image' : selection.type} readOnly />
            </div>
            {selection.isConnector && (
              <div className="field">
                <label htmlFor="sel-points">Points Count</label>
                <input id="sel-points" value={selection.pointsCount ?? 2} readOnly />
              </div>
            )}
            {selection.pdfSource && (
              <div className="props-subgroup">
                <div className="field">
                  <label htmlFor="sel-pdf-src" title="The source PDF this crop was rendered from">Source PDF</label>
                  <input id="sel-pdf-src" value={selection.pdfSource} readOnly title={selection.pdfSource} />
                </div>
                <div className="field-row">
                  <div className="field">
                    <label htmlFor="sel-pdf-page" title="1-based PDF page">Page</label>
                    <input id="sel-pdf-page" value={(selection.pdfPage ?? 0) + 1} readOnly />
                  </div>
                  <div className="field">
                    <label htmlFor="sel-pdf-dpi" title="Render resolution of this crop">Crop DPI</label>
                    <input id="sel-pdf-dpi" value={selection.pdfDpi ?? ''} readOnly />
                  </div>
                </div>
                {selection.pdfCrop && (
                  <div className="field">
                    <label htmlFor="sel-pdf-crop" title="Crop rectangle in PDF points (x0,y0,x1,y1)">Crop Rectangle (pt)</label>
                    <input id="sel-pdf-crop" value={selection.pdfCrop} readOnly title={selection.pdfCrop} />
                  </div>
                )}
              </div>
            )}
            {selection.name !== undefined && (
              <div className="field">
                <label htmlFor="sel-name">Object Name</label>
                <input id="sel-name" type="text" title="A label for this object (does not appear on the sheet)" value={selection.name} onChange={(e) => onUpdateSelection({ name: e.target.value })} />
              </div>
            )}
            {selection.isText && (
              <div className="field">
                <label htmlFor="sel-text">Text</label>
                <textarea
                  id="sel-text"
                  rows={3}
                  value={selection.text || ''}
                  onChange={(e) => onUpdateSelection({ text: e.target.value })}
                />
              </div>
            )}
            {selection.smartComponentType && selection.smartConfig ? (
              <div className="props-subgroup">
                <div className="field">
                  <label>Smart Component</label>
                  <input value={SMART_COMPONENT_LABELS[selection.smartComponentType]} readOnly />
                </div>
                <p className="props-note">
                  Parameter edits regenerate the grouped vector component. Explode keeps every child shape and label independently editable.
                </p>
                <div className="field-row">
                  <button className="props-btn" type="button" onClick={onEditSmartComponent}>
                    Edit Smart Component
                  </button>
                  <button className="props-btn" type="button" onClick={onExplodeSmartComponent}>
                    Explode Smart Component
                  </button>
                </div>
              </div>
            ) : null}
            {selection.calloutConfig ? (
              <div className="props-subgroup">
                <div className="field">
                  <label>Callout Family</label>
                  <input value={selection.calloutConfig.family === 'round' ? 'Round Callouts' : selection.calloutConfig.family === 'square' ? 'Square Callouts' : 'Callout Blocks / Lists'} readOnly />
                </div>
                <button className="props-btn" type="button" onClick={onEditCallout}>
                  Edit Callout Set
                </button>
              </div>
            ) : null}
            {selection.isPlacedSymbol && !selection.calloutConfig ? (
              <div className="props-subgroup">
                <p className="props-note">
                  Category: {selection.symCategory || 'custom'}{selection.favorite ? ' · Favorite' : ''}
                </p>
                <button className="props-btn" type="button" onClick={onEditPlacedSymbol}>
                  Edit Symbol / Component
                </button>
              </div>
            ) : null}
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
                {selection.isImage && selection.pdfSource && (
                  <div className="field-row">
                    <button
                      className="props-btn"
                      title="Scale this PDF crop to the full printable sheet width"
                      onClick={() => {
                        const w = Math.max(1, selection.width ?? 1);
                        const h = Math.max(1, selection.height ?? 1);
                        const ratio = h / w;
                        const fitW = BODY_W * 0.95;
                        onUpdateSelection({ width: fitW, height: fitW * ratio });
                      }}
                    >
                      Fit Width
                    </button>
                    <button
                      className="props-btn"
                      title="Scale this PDF crop to fit inside the printable sheet body"
                      onClick={() => {
                        const w = Math.max(1, selection.width ?? 1);
                        const h = Math.max(1, selection.height ?? 1);
                        const s = Math.min((BODY_W * 0.95) / w, (BODY_H * 0.95) / h);
                        onUpdateSelection({ width: w * s, height: h * s });
                      }}
                    >
                      Fit to Sheet Body
                    </button>
                  </div>
                )}
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
            {!selection.isImage && (
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
              </>
            )}
            {selection.isConnector && (
              <>
                <div className="field">
                  <label htmlFor="sel-arrowhead">Arrowhead</label>
                  <select
                    id="sel-arrowhead"
                    value={selection.arrowStart && selection.arrowEnd ? 'both' : selection.arrowStart ? 'start' : selection.arrowEnd ? 'end' : 'none'}
                    onChange={(e) => {
                      const v = e.target.value;
                      onUpdateSelection({
                        arrowStart: v === 'start' || v === 'both',
                        arrowEnd: v === 'end' || v === 'both',
                      });
                    }}
                  >
                    <option value="none">None</option>
                    <option value="start">Start</option>
                    <option value="end">End</option>
                    <option value="both">Both</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="sel-conn-label">Label</label>
                  <input id="sel-conn-label" value={selection.label ?? ''} onChange={(e) => onUpdateSelection({ label: e.target.value })} />
                </div>
                <div className="field-row">
                  <button className="props-btn" onClick={() => onConnectorAddVertex?.()}>Add Vertex</button>
                  <button className="props-btn" onClick={() => onConnectorDeleteVertex?.()}>Delete Vertex</button>
                </div>
                <div className="field-row">
                  <button className="props-btn" onClick={() => onConnectorConvert?.('line')}>To Line</button>
                  <button className="props-btn" onClick={() => onConnectorConvert?.('elbow')}>To Elbow</button>
                </div>
                <div className="field-row">
                  <button className="props-btn" onClick={() => onConnectorConvert?.('polyline')}>To Polyline</button>
                  <button className="props-btn" onClick={() => onConnectorReverse?.()}>Reverse Direction</button>
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
