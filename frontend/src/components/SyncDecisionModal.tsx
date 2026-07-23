import type { WorkbookLinkStatus } from '../api/client';

interface Props {
  status: WorkbookLinkStatus;
  projectName: string;
  busy?: boolean;
  onClose: () => void;
  onResolve: (direction: 'workbook_to_app' | 'app_to_workbook') => Promise<void>;
}

export default function SyncDecisionModal({ status, projectName, busy, onClose, onResolve }: Props) {
  const workbookName = status.workbook?.projectName || status.workbook?.filename || 'Linked workbook';
  return (
    <div className="dashboard-overlay sync-decision-overlay" role="dialog" aria-modal="true">
      <div className="sync-decision-modal">
        <header>
          <div>
            <div className="eyebrow">SAFE SYNCHRONIZATION REVIEW</div>
            <h2>Choose which structure should be used</h2>
            <p>No action happens until you choose. A matched project.json and workbook backup is created first.</p>
          </div>
          <button type="button" onClick={onClose} disabled={busy}>Cancel — Make No Changes</button>
        </header>

        <div className="sync-state-summary">
          <div><b>Active app project</b><span>{projectName}</span></div>
          <div><b>Linked workbook</b><span>{workbookName}</span></div>
          <div><b>Current state</b><span>{status.message}</span></div>
        </div>

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
            Create Backup, Then Import Workbook Structure into App
          </button>
        </section>

        <section className="sync-choice app-choice">
          <div>
            <h3>Use App Structure</h3>
            <p><b>Choose this when the app has the correct page order, codes, titles, Include/Exclude choices, or statuses.</b></p>
            <ul>
              <li>Updates 00_INDEX, workbook tab order, status colors, and companion sheets.</li>
              <li>Keeps existing worksheet cells, formulas, images, merges, and manual app drawings.</li>
              <li>Does not replace the app project with a new project.</li>
            </ul>
          </div>
          <button type="button" className="primary" disabled={busy} onClick={() => void onResolve('app_to_workbook')}>
            Create Backup, Then Write App Structure into Workbook
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
