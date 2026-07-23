import type { WorkbookQualityReport } from '../api/client';

interface Props {
  report: WorkbookQualityReport | null;
  busy?: boolean;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onRepair: (mode: 'safe' | 'strict') => Promise<void>;
}

export default function WorkbookQualityModal({ report, busy, onClose, onRefresh, onRepair }: Props) {
  return (
    <div className="dashboard-overlay" role="dialog" aria-modal="true">
      <div className="dashboard-overlay-panel workbook-quality-modal">
        <div className="overlay-head">
          <div>
            <h2>Workbook Inspector & Recovery</h2>
            <p>Automatic audit first. No formulas or technical values are guessed.</p>
          </div>
          <div>
            <button type="button" disabled={busy} onClick={() => void onRefresh()}>Run Audit Again</button>
            <button type="button" onClick={onClose} disabled={busy}>Close</button>
          </div>
        </div>

        {!report ? (
          <div className="quality-empty">Link a workbook, then run the audit.</div>
        ) : (
          <div className="quality-body">
            <div className="quality-counts">
              <div><b>{report.counts.sheets}</b><span>Workbook sheets</span></div>
              <div><b>{report.counts.indexRows}</b><span>00_INDEX rows</span></div>
              <div><b>{report.counts.unindexedSheets}</b><span>Unindexed sheets</span></div>
              <div><b>{report.counts.formulaErrors}</b><span>Formula/error cells</span></div>
              <div><b>{report.counts.errors}</b><span>Errors</span></div>
              <div><b>{report.counts.warnings}</b><span>Warnings</span></div>
            </div>

            <div className="quality-actions">
              <section>
                <h3>Safe Structural Repair</h3>
                <p>Creates a backup, repairs 00_INDEX schema, registers added sheets as excluded, restores order/Page IDs/status fields, tab colors, dropdowns, and control-sheet formatting.</p>
                <button type="button" className="primary" disabled={busy} onClick={() => void onRepair('safe')}>Backup, Then Apply Safe Repair</button>
              </section>
              <section>
                <h3>Strict Table Formatting</h3>
                <p>Includes Safe Repair, then normalizes indexed table/schedule fonts to Arial 8 and consistent cell borders. Images, merges, row heights, and column widths are preserved.</p>
                <button type="button" disabled={busy} onClick={() => void onRepair('strict')}>Backup, Then Apply Strict Formatting</button>
              </section>
            </div>

            <div className="quality-warning">
              Formula errors are reported for review. The tool never invents formulas, controller IDs, quantities, dates, technical values, or project scope.
            </div>

            <div className="quality-issues">
              {report.issues.length ? report.issues.map((issue, index) => (
                <article key={`${issue.code}-${index}`} className={`quality-issue ${issue.severity}`}>
                  <div><b>{issue.severity.toUpperCase()}</b><strong>{issue.message}</strong></div>
                  {issue.items && <pre>{JSON.stringify(issue.items, null, 2)}</pre>}
                </article>
              )) : <div className="quality-clean">No structural issues were found.</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
