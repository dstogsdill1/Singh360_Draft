import { useMemo, useState, type ChangeEvent, type MouseEvent } from 'react';
import type { PageModel } from '../model/types';

export interface ExportRevisionResult {
  updateRevision: boolean;
  newRevision: string;
  notes: string;
}

interface Props {
  currentRevision: string;
  packageName: string;
  pages: PageModel[];
  onExport: (width: number, height: number, rev: ExportRevisionResult, pageIds: string[]) => void;
  onCancel: () => void;
}

export default function ExportModal({ currentRevision, packageName, pages, onExport, onCancel }: Props) {
  const includedPages = useMemo(
    () => pages.filter((page) => page.include).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [pages],
  );
  const [updateRev, setUpdateRev] = useState(false);
  const [revMode, setRevMode] = useState<'increment' | 'custom'>('increment');
  const [customRev, setCustomRev] = useState('');
  const [revNotes, setRevNotes] = useState('');

  const nextRevision = (() => {
    if (revMode === 'custom') return customRev.trim() || currentRevision;
    const match = currentRevision.match(/(\d+)\s*$/);
    if (match) return currentRevision.replace(/\d+\s*$/, String(parseInt(match[1], 10) + 1));
    return currentRevision ? `${currentRevision} Rev 1` : 'V1';
  })();

  const orderedIncluded = includedPages.map((page) => page.id);

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide export-pages-modal" onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>Export PDF</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body export-pages-body">
          <section className="export-options-column">
            <p className="renumber-note">
              Output is always the complete current drawing set on ANSI B 17&quot; × 11&quot; landscape sheets. Original PDF pages are restored from the project-local source so born-digital linework stays sharp.
            </p>

            <div className="export-rev">
              <div className="field">
                <label>Current Revision</label>
                <div className="props-path">{currentRevision || '(none)'} · Package: {packageName || '(project name)'}</div>
              </div>
              <label className="lib-showretired" title="Record a new revision in the title block and revision history when you export">
                <input type="checkbox" checked={updateRev} onChange={(event: ChangeEvent<HTMLInputElement>) => setUpdateRev(event.target.checked)} /> Update revision on export
              </label>
              {updateRev && (
                <>
                  <div className="field">
                    <label htmlFor="rev-mode">Revision</label>
                    <select id="rev-mode" value={revMode} onChange={(event: ChangeEvent<HTMLSelectElement>) => setRevMode(event.target.value as 'increment' | 'custom')}>
                      <option value="increment">Increment → {nextRevision}</option>
                      <option value="custom">Set custom…</option>
                    </select>
                  </div>
                  {revMode === 'custom' && (
                    <div className="field">
                      <label htmlFor="rev-custom">Custom Revision</label>
                      <input id="rev-custom" type="text" placeholder="V2" value={customRev} onChange={(event: ChangeEvent<HTMLInputElement>) => setCustomRev(event.target.value)} />
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor="rev-notes">Revision Notes</label>
                    <input id="rev-notes" type="text" placeholder="Description of this revision" value={revNotes} onChange={(event: ChangeEvent<HTMLInputElement>) => setRevNotes(event.target.value)} />
                  </div>
                </>
              )}
            </div>
          </section>

          <section className="export-page-picker">
            <div className="export-page-picker-head">
              <div>
                <strong>Pages to export</strong>
                <span>{includedPages.length} included page{includedPages.length === 1 ? '' : 's'}, in saved project order</span>
              </div>
            </div>
            <div className="export-page-list">
              {includedPages.map((page) => (
                <div key={page.id} className="export-page-row selected">
                  <span className="export-page-number">{page.pageNumber ?? page.order}</span>
                  <span className="export-page-code">{page.displaySheetCode || page.sheetCode || '—'}</span>
                  <span className="export-page-title">{page.sheetTitle}</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="modal-foot">
          <span className="export-selection-note">
            {includedPages.length ? `${includedPages.length} included page${includedPages.length === 1 ? '' : 's'} will be regenerated.` : 'Include at least one page before export.'}
          </span>
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button
            className="btn btn-primary"
            disabled={orderedIncluded.length === 0}
            onClick={() => onExport(
              17,
              11,
              { updateRevision: updateRev, newRevision: nextRevision, notes: revNotes },
              orderedIncluded,
            )}
          >
            Export Complete PDF
          </button>
        </div>
      </div>
    </div>
  );
}
