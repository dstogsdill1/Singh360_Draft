import type { PageModel, ViewMode } from '../model/types';
import type { ViewControls } from './Ribbon';
import { PAGE_ISSUE_STATUSES, normalizePageIssueStatus } from '../model/pageStatus';

interface Props {
  activePage: PageModel;
  view: ViewControls;
  viewMode: ViewMode;
  sourceWorksheetName?: string;
  sourceOnly?: boolean;
  sourceDirty?: boolean;
  sourceStatusLabel?: string;
  onViewModeChange: (mode: ViewMode) => void;
  onPublishSource?: () => void;
  onRebuildFromSource?: () => void;
  canRebuildFromSource?: boolean;
  onRestorePageRebuild?: () => void;
  canRestorePageRebuild?: boolean;
  onPatchPage?: (patch: Partial<PageModel>) => void;
  onOpenHelp?: () => void;
}

export default function ViewportToolbar({
  activePage,
  view,
  viewMode,
  sourceWorksheetName,
  sourceOnly,
  sourceDirty,
  sourceStatusLabel,
  onViewModeChange,
  onPublishSource,
  onRebuildFromSource,
  canRebuildFromSource,
  onRestorePageRebuild,
  canRestorePageRebuild,
  onPatchPage,
  onOpenHelp,
}: Props) {
  const pageLabel = sourceOnly && viewMode === 'source'
    ? 'Source-only worksheet'
    : activePage.pageNumber != null
      ? `Page ${activePage.pageNumber} of ${activePage.pageTotal ?? '—'}`
      : 'Not included';
  const displayCode = viewMode === 'source' && sourceOnly ? 'DRAFT' : activePage.sheetCode;
  const displayTitle = viewMode === 'source' && sourceWorksheetName ? sourceWorksheetName : activePage.sheetTitle;

  return (
    <div className="viewport-toolbar">
      <span className="vt-label">
        <span className="vt-code">{displayCode}</span>
        {displayTitle}
        {sourceOnly && viewMode === 'source' ? <em className="vt-source-only">Source only</em> : null}
      </span>
      <span className="vt-viewmode">
        {sourceOnly && viewMode === 'source' ? (
          <button className="fit-btn publish-source" onClick={onPublishSource} disabled={!onPublishSource}>Publish Worksheet</button>
        ) : (
          <button className={`fit-btn ${viewMode === 'normalized' ? 'active' : ''}`} onClick={() => onViewModeChange('normalized')}>Drawing</button>
        )}
        <button className={`fit-btn ${viewMode === 'source' ? 'active' : ''}`} onClick={() => onViewModeChange('source')}>Workbook Draft</button>
        {canRebuildFromSource && onRebuildFromSource ? (
          <button className="fit-btn" type="button" onClick={onRebuildFromSource} title="Rebuild this Published page from the linked Draft worksheet">Rebuild Published Page From Draft</button>
        ) : null}
        {canRestorePageRebuild && onRestorePageRebuild ? (
          <button className="fit-btn" type="button" onClick={onRestorePageRebuild} title="Restore the page from before the last rebuild (Ctrl+Z)">Restore Last Page Rebuild</button>
        ) : null}
        {sourceStatusLabel ? <span className="vt-source-status sb-item">{sourceStatusLabel}</span> : null}
      </span>
      <span className="vt-issue-status">
        {PAGE_ISSUE_STATUSES.map((status) => {
          const active = normalizePageIssueStatus(activePage.issueStatus) === status.value;
          return (
            <button
              key={status.value}
              type="button"
              className={`vt-status-btn status-${status.value} ${active ? 'active' : ''}`}
              title={`Set page status to ${status.label}`}
              onClick={() => onPatchPage?.({
                issueStatus: status.value,
                statusUpdatedAt: new Date().toISOString(),
                statusConfirmedAt: status.confirmed ? new Date().toISOString() : undefined,
              })}
            >
              {status.confirmed ? '✓ ' : ''}{status.label}
            </button>
          );
        })}
        <button
          type="button"
          className={`fit-btn vt-include-btn ${activePage.include ? 'included' : 'excluded'}`}
          onClick={() => onPatchPage?.({ include: !activePage.include })}
        >
          {activePage.include ? 'Included in Drawing Set' : 'Excluded from Drawing Set'}
        </button>
        <button type="button" className="fit-btn vt-help-btn" onClick={onOpenHelp}>Open Help</button>
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
