import { useState } from 'react';
import type { ExportWarning } from '../api/client';

interface Props {
  warnings: ExportWarning[];
  onClose: () => void;
  onExportAnyway: () => Promise<void>;
}

export default function ExportWarningsModal({ warnings, onClose, onExportAnyway }: Props) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [exporting, setExporting] = useState(false);

  return (
    <div className="modal-backdrop" onClick={() => { if (!exporting) onClose(); }}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Export Warnings — Review Before PDF</h2>
          <button className="modal-x" onClick={onClose} title="Close" disabled={exporting}>×</button>
        </div>
        <div className="modal-body">
          <p className="cw-note">
            The PDF can be exported, but these issues were detected. Review the list below.
            You can cancel and fix them, or continue exporting anyway.
          </p>
          <table className="op-table">
            <thead>
              <tr>
                <th>Sheet</th>
                <th>Title</th>
                <th>Issue</th>
                <th>Suggested fix</th>
              </tr>
            </thead>
            <tbody>
              {warnings.map((w, i) => (
                <tr key={`${w.pageCode}-${i}`}>
                  <td>{w.pageCode || '—'}</td>
                  <td>{w.pageTitle || '—'}</td>
                  <td>{w.issue}</td>
                  <td>{w.suggestedFix}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <label className="export-warn-ack" style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginTop: 14 }}>
            <input
              type="checkbox"
              checked={acknowledged}
              disabled={exporting}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            <span>I understand these warnings and want to export anyway.</span>
          </label>
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose} disabled={exporting}>Cancel / Go Back</button>
          <button
            className="btn btn-primary"
            disabled={!acknowledged || exporting}
            onClick={async () => {
              if (!acknowledged) return;
              setExporting(true);
              try {
                await onExportAnyway();
              } finally {
                setExporting(false);
              }
            }}
          >
            {exporting ? 'Saving and Rechecking…' : 'Export Anyway'}
          </button>
        </div>
      </div>
    </div>
  );
}
