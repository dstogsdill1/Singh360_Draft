import type { PageModel, ViewMode } from '../model/types';
import type { ViewControls } from './Ribbon';

interface Props {
  activePage: PageModel;
  view: ViewControls;
  viewMode: ViewMode;
  sourceDirty?: boolean;
  sourceStatusLabel?: string;
  onViewModeChange: (mode: ViewMode) => void;
  onRebuildFromSource?: () => void;
  canRebuildFromSource?: boolean;
  onRestorePageRebuild?: () => void;
  canRestorePageRebuild?: boolean;
  onCleanHiddenArtifacts?: () => void;
  canCleanHiddenArtifacts?: boolean;
  layoutEditing?: boolean;
  canEditPageLayout?: boolean;
  onTogglePageLayout?: () => void;
  onResetPageLayout?: () => void;
  onUndo?: () => void;
  canUndo?: boolean;
  onRedo?: () => void;
  canRedo?: boolean;
}

export default function ViewportToolbar({
  activePage,
  view,
  viewMode,
  sourceStatusLabel,
  onViewModeChange,
  onCleanHiddenArtifacts,
  canCleanHiddenArtifacts,
  layoutEditing,
  canEditPageLayout,
  onTogglePageLayout,
  onResetPageLayout,
  onUndo,
  canUndo,
  onRedo,
  canRedo,
}: Props) {
  const pageLabel =
    activePage.pageNumber != null
      ? `Page ${activePage.pageNumber} of ${activePage.pageTotal ?? '—'}`
      : 'Not included';

  return (
    <div className="viewport-toolbar">
      <span className="vt-label">
        <span className="vt-code">{activePage.sheetCode}</span>
        {activePage.sheetTitle}
      </span>

      <span className="vt-viewmode">
        <button
          className={`fit-btn ${viewMode === 'normalized' ? 'active' : ''}`}
          onClick={() => onViewModeChange('normalized')}
          title="Finished printable sheet"
        >
          Page
        </button>
        <button
          className={`fit-btn ${viewMode === 'source' ? 'active' : ''}`}
          onClick={() => onViewModeChange('source')}
          title="Workbook cell values and source formatting"
        >
          Data
        </button>

        {canEditPageLayout && onTogglePageLayout ? (
          <button
            type="button"
            className={`fit-btn vt-page-layout ${layoutEditing ? 'active' : ''}`}
            onClick={onTogglePageLayout}
            title="Drag the actual output-table boundaries on the finished sheet"
          >
            {layoutEditing ? 'Finish Layout' : 'Edit Layout'}
          </button>
        ) : null}

        <button
          type="button"
          className="fit-btn"
          onClick={onUndo}
          disabled={!canUndo}
          title={viewMode === 'source' ? 'Undo the last data edit (Ctrl+Z)' : 'Undo the last page-layout edit (Ctrl+Z)'}
        >
          Undo
        </button>
        <button
          type="button"
          className="fit-btn"
          onClick={onRedo}
          disabled={!canRedo}
          title={viewMode === 'source' ? 'Redo the last data edit (Ctrl+Y)' : 'Redo the last page-layout edit (Ctrl+Y)'}
        >
          Redo
        </button>

        {canEditPageLayout && layoutEditing && onResetPageLayout ? (
          <button
            type="button"
            className="fit-btn"
            onClick={onResetPageLayout}
            title="Restore the standard Singh360 layout for this page"
          >
            Reset Layout
          </button>
        ) : null}

        {canCleanHiddenArtifacts && onCleanHiddenArtifacts ? (
          <button
            className="fit-btn vt-clean-artifacts"
            type="button"
            onClick={onCleanHiddenArtifacts}
          >
            Clean Hidden Artifacts
          </button>
        ) : null}

        {sourceStatusLabel ? <span className="vt-source-status sb-item">{sourceStatusLabel}</span> : null}
      </span>

      <span className="vt-spacer" />
      <span className="sb-item">{pageLabel}</span>
      <button className={`fit-btn ${view.fitMode === 'width' ? 'active' : ''}`} onClick={() => view.setFitMode('width')}>Fit Width</button>
      <button className={`fit-btn ${view.fitMode === 'page' ? 'active' : ''}`} onClick={() => view.setFitMode('page')}>Fit Page</button>
      <button className={`fit-btn ${view.fitMode === 'actual' ? 'active' : ''}`} onClick={view.setActual}>100%</button>
      <button className="fit-btn" onClick={view.zoomOut}>−</button>
      <span className="vt-zoom">{view.zoomPct}%</span>
      <button className="fit-btn" onClick={view.zoomIn}>+</button>
      <button className={`fit-btn ${view.showGrid ? 'active' : ''}`} onClick={view.toggleGrid}>Grid</button>
    </div>
  );
}
