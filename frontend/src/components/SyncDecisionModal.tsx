import type { WorkbookLinkStatus } from '../api/client';

// S360 FULL WORKBOOK MIRROR UX V25

interface Props {
  status: WorkbookLinkStatus;
  projectName: string;
  projectSavedAt?: string;
  busy?: boolean;
  onClose: () => void;
  onResolve: (direction: 'workbook_to_app' | 'app_to_workbook' | 'baseline') => Promise<void>;
}

export default function SyncDecisionModal({ status, projectName, projectSavedAt, busy, onClose, onResolve }: Props) {
  const workbookName = status.workbook?.projectName || status.workbook?.filename || 'Linked workbook';
  const workbookModified = status.workbook?.modified || '';
  const workbookTime = workbookModified ? Date.parse(workbookModified) : Number.NaN;
  const projectTime = projectSavedAt ? Date.parse(projectSavedAt) : Number.NaN;
  const workbookNewer = Number.isFinite(workbookTime) && (!Number.isFinite(projectTime) || workbookTime > projectTime);
  const projectNewer = Number.isFinite(projectTime) && (!Number.isFinite(workbookTime) || projectTime > workbookTime);
  return (
    <div className="dashboard-overlay sync-decision-overlay" role="dialog" aria-modal="true">
      <div className="sync-decision-modal">
        <header>
          <div>
            <div className="eyebrow">SAFE SYNCHRONIZATION REVIEW</div>
            <h2>Which version was edited last?</h2>
            <p>Green means matching. Yellow means one side changed. Red means both changed or the wrong workbook is linked. A backup is created before either version is used.</p>
          </div>
          <button type="button" onClick={onClose} disabled={busy}>Cancel — Make No Changes</button>
        </header>

        <div className="sync-state-summary simple">
          <div className={projectNewer ? 'newer' : ''}><b>Singh360 Project</b><span>{projectName}</span><small>Last save: {projectSavedAt || 'Not recorded'}</small></div>
          <div className={workbookNewer ? 'newer' : ''}><b>Excel Workbook</b><span>{workbookName}</span><small>Last edit: {workbookModified || 'Not recorded'}</small></div>
          <div><b>What is different?</b><span>{status.message}</span></div>
        </div>

        {status.status === 'review_required' && (
          <section className="sync-choice match-choice">
            <div>
              <h3>They Match</h3>
              <p><b>Choose this when the workbook and project already represent the same current drawing set.</b></p>
              <p>Neither version replaces the other. Singh360 records the matching baseline and opens normally.</p>
            </div>
            <button type="button" className="primary" disabled={busy} onClick={() => void onResolve('baseline')}>
              They Match — Link and Continue
            </button>
          </section>
        )}

        <section className="sync-choice workbook-choice">
          <div>
            <h3>Use Workbook Structure</h3>
            <p><b>Choose this when Excel has the correct page list, order, sheet codes, titles, Include/Exclude choices, or status values.</b></p>
            <ul>
              <li>Updates the app page manifest from 00_INDEX.</li>
              <li>Keeps app drawings, pasted images, crops, symbols, highlights, components, and canvas objects.</li>
              <li>Does not delete the linked workbook.</li>
            </ul>
          </div>
          <button type="button" className="primary" disabled={busy} onClick={() => void onResolve('workbook_to_app')}>
            Use Workbook
          </button>
        </section>

        <section className="sync-choice app-choice">
          <div>
            <h3>Sync Project to Workbook</h3>
            <p><b>Choose this when Singh360 has the correct base-page order, codes, titles, Include/Exclude choices, or statuses.</b></p>
            <ul>
              <li>Mirrors every Singh360 base page into 00_INDEX and the physical workbook tab order.</li>
              <li>Creates missing companion worksheets, grays excluded tabs, and preserves existing worksheet cells, formulas, images, merges, and app drawings.</li>
              <li>Does not replace the app project with a new project.</li>
            </ul>
          </div>
          <button type="button" className="primary" disabled={busy} onClick={() => void onResolve('app_to_workbook')}>
            Sync Project to Workbook Now
          </button>
        </section>

        <footer>
          <strong>Automatic fail-safe:</strong>
          <span>A timestamped copy of both sides is stored under .docs/backups/workbook_resolution before either action runs.</span>
        </footer>
      </div>
    </div>
  );
}
