import type { PageModel, ViewMode } from '../model/types';
import type { PageReviewFilter, ViewControls } from './Ribbon';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';
import '../styles/rapidPageReview.css';
import { PAGE_ISSUE_STATUSES, normalizePageIssueStatus } from '../model/pageStatus';

interface Props {
  activePage: PageModel;
  view: ViewControls;
  viewMode: ViewMode;
  sourceWorksheetName?: string;
  hasImportedTableSource: boolean;
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
  reviewPages: PageModel[];
  pageFilter: PageReviewFilter;
  rapidReviewBusy: boolean;
  onNavigateReview: (direction: -1 | 1) => void;
  onToggleIncludeAndAdvance: () => void;
}

export default function ViewportToolbar({
  activePage,
  view,
  viewMode,
  sourceWorksheetName,
  hasImportedTableSource,
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
  reviewPages,
  pageFilter,
  rapidReviewBusy,
  onNavigateReview,
  onToggleIncludeAndAdvance,
}: Props) {
  const pageLabel = sourceOnly && viewMode === 'source'
    ? 'Source-only worksheet'
    : activePage.pageNumber != null
      ? `Page ${activePage.pageNumber} of ${activePage.pageTotal ?? '—'}`
      : 'Not included';
  const displayCode = viewMode === 'source' && sourceOnly ? 'DRAFT' : activePage.sheetCode;
  const displayTitle = viewMode === 'source' && sourceWorksheetName ? sourceWorksheetName : activePage.sheetTitle;
  // S360 RAPID PAGE REVIEW V35
  const reviewIndex = reviewPages.findIndex((page) => page.id === activePage.id);
  const filterLabel = pageFilter === 'included' ? 'Included only' : pageFilter === 'excluded' ? 'Not included' : 'All pages';
  const filterPosition = reviewIndex >= 0 ? reviewIndex + 1 : 0;
  const includeLocked = isCoverPage(activePage) || isSheetIndexPage(activePage);
  const canPrevious = reviewPages.length > 0 && (reviewIndex < 0 || reviewIndex > 0);
  const canNext = reviewPages.length > 0 && (reviewIndex < 0 || reviewIndex < reviewPages.length - 1);

  return (
    <div className="viewport-toolbar">
      <span className="vt-label">
        <span className="vt-code">{displayCode}</span>
        {displayTitle}
        {sourceOnly && viewMode === 'source' ? <em className="vt-source-only">Source only</em> : null}
      </span>
      <span className="vt-viewmode">
        <button className={`fit-btn ${viewMode === 'normalized' ? 'active' : ''}`} onClick={() => onViewModeChange('normalized')}>Drawing</button>
        {hasImportedTableSource ? (
          <>
            <button
              className={`fit-btn ${viewMode === 'spreadsheet' ? 'active' : ''}`}
              onClick={() => onViewModeChange('spreadsheet')}
              title="Edit this page's worksheet in the Univer spreadsheet editor"
            >Spreadsheet</button>
            {sourceOnly && viewMode === 'source' ? (
              <button className="fit-btn publish-source" onClick={onPublishSource} disabled={!onPublishSource}>Add Imported Table as Drawing Page</button>
            ) : null}
            <button className={`fit-btn ${viewMode === 'source' ? 'active' : ''}`} onClick={() => onViewModeChange('source')}>Source Data</button>
            {canRebuildFromSource && onRebuildFromSource ? (
              <button className="fit-btn" type="button" onClick={onRebuildFromSource} title="Rebuild this drawing from its project-local imported table data">Rebuild Drawing</button>
            ) : null}
          </>
        ) : null}
        {canRestorePageRebuild && onRestorePageRebuild ? (
          <button className="fit-btn" type="button" onClick={onRestorePageRebuild} title="Restore the page from before the last rebuild (Ctrl+Z)">Restore Last Rebuild</button>
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
              disabled={includeLocked}
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
          disabled={includeLocked}
          onClick={() => onPatchPage?.({ include: !activePage.include })}
          title={includeLocked ? 'Cover and Sheet Index are required app-managed pages' : 'Include or exclude this page from the drawing set'}
        >
          {activePage.include ? 'Included in Drawing Set' : 'Excluded from Drawing Set'}
        </button>
        <button type="button" className="fit-btn vt-help-btn" onClick={onOpenHelp}>Open Help</button>
      </span>
      <span className="vt-spacer" />
      <span className={`vt-page-filter-widget filter-${pageFilter}`}>{filterLabel} · {filterPosition} of {reviewPages.length}</span>
      <button type="button" className="fit-btn vt-review-nav" disabled={!canPrevious || rapidReviewBusy} onClick={() => onNavigateReview(-1)}>← Previous</button>
      <button
        type="button"
        className={`fit-btn vt-rapid-include ${activePage.include ? 'included' : 'excluded'}`}
        disabled={includeLocked || rapidReviewBusy}
        onClick={onToggleIncludeAndAdvance}
        title={includeLocked ? 'Cover and Sheet Index are required pages' : 'Toggle Include, save automatically, then advance'}
      >
        {rapidReviewBusy ? 'Saving…' : `Include in Drawing: ${activePage.include ? 'YES' : 'NO'} →`}
      </button>
      <button type="button" className="fit-btn vt-review-nav" disabled={!canNext || rapidReviewBusy} onClick={() => onNavigateReview(1)}>Next →</button>
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
