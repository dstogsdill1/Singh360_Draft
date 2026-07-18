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
}

export default function ViewportToolbar({
  activePage,
  view,
  viewMode,
  sourceDirty,
  sourceStatusLabel,
  onViewModeChange,
  onRebuildFromSource,
  canRebuildFromSource,
  onRestorePageRebuild,
  canRestorePageRebuild,
  onCleanHiddenArtifacts,
  canCleanHiddenArtifacts,
  layoutEditing,
  canEditPageLayout,
  onTogglePageLayout,
  onResetPageLayout,
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
        >
          Normalized
        </button>
        <button
          className={`fit-btn ${viewMode === 'source' ? 'active' : ''}`}
          onClick={() => onViewModeChange('source')}
        >
          Source Data
        </button>

        {canEditPageLayout && onTogglePageLayout ? (
          <button
            type="button"
            className={`fit-btn vt-page-layout ${layoutEditing ? 'active' : ''}`}
            onClick={onTogglePageLayout}
            title="Resize the actual printable normalized table directly on the sheet"
          >
            {layoutEditing ? 'Finish Page Layout' : 'Edit Page Layout'}
          </button>
        ) : null}

        {canEditPageLayout && layoutEditing && onResetPageLayout ? (
          <button
            type="button"
            className="fit-btn"
            onClick={onResetPageLayout}
            title="Discard manual output geometry and restore the Singh360 standard for this page"
          >
            Reset Standard Layout
          </button>
        ) : null}

        {canRebuildFromSource && onRebuildFromSource ? (
          <button
            className="fit-btn"
            type="button"
            onClick={onRebuildFromSource}
            title="Refresh values and styles from Source Data while preserving a manual Page Layout"
          >
            Refresh From Source
          </button>
        ) : null}

        {canRestorePageRebuild && onRestorePageRebuild ? (
          <button
            className="fit-btn"
            type="button"
            onClick={onRestorePageRebuild}
            title="Restore the page from before the last refresh"
          >
            Restore Last Refresh
          </button>
        ) : null}

        {canCleanHiddenArtifacts && onCleanHiddenArtifacts ? (
          <button
            className="fit-btn vt-clean-artifacts"
            type="button"
            onClick={onCleanHiddenArtifacts}
            title="Remove tiny hidden overlay fragments from this cover page"
          >
            Clean Hidden Artifacts
          </button>
        ) : null}

        {sourceStatusLabel ? (
          <span className="vt-source-status sb-item">{sourceStatusLabel}</span>
        ) : null}
      </span>

      <span className="vt-spacer" />
      <span className="sb-item">{pageLabel}</span>
      <button className={`fit-btn ${view.fitMode === 'width' ? 'active' : ''}`} onClick={() => view.setFitMode('width')}>Fit Width</button>
      <button className={`fit-btn ${view.fitMode === 'page' ? 'active' : ''}`} onClick={() => view.setFitMode('page')}>Fit Page</button>
      <button className={`fit-btn ${view.fitMode === 'actual' ? 'active' : ''}`} onClick={view.setActual}>100%</button>
      <button className="fit-btn" onClick={view.zoomOut} title="Zoom out">−</button>
      <span className="vt-zoom">{view.zoomPct}%</span>
      <button className="fit-btn" onClick={view.zoomIn} title="Zoom in">+</button>
      <button className={`fit-btn ${view.showGrid ? 'active' : ''}`} onClick={view.toggleGrid} title="Toggle grid">Grid</button>
    </div>
  );
}
