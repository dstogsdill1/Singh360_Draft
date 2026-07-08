import type { PageModel, ViewMode } from '../model/types';
import type { ViewControls } from './Ribbon';

interface Props {
  activePage: PageModel;
  view: ViewControls;
  viewMode: ViewMode;
  sourceDirty?: boolean;
  onViewModeChange: (mode: ViewMode) => void;
  onRefreshFromSource?: () => void;
}

export default function ViewportToolbar({
  activePage,
  view,
  viewMode,
  sourceDirty,
  onViewModeChange,
  onRefreshFromSource,
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
        <button className={`fit-btn ${viewMode === 'normalized' ? 'active' : ''}`} onClick={() => onViewModeChange('normalized')}>Normalized</button>
        <button className={`fit-btn ${viewMode === 'source' ? 'active' : ''}`} onClick={() => onViewModeChange('source')}>Source</button>
        {viewMode === 'normalized' && sourceDirty && onRefreshFromSource ? (
          <button className="fit-btn" type="button" onClick={onRefreshFromSource} title="Rebuild normalized page from source">
            Refresh From Source
          </button>
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
