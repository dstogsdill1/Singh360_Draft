import type { ExportWarning } from '../api/client';

interface Props {
  warnings: ExportWarning[];
  onClose: () => void;
}

export default function ExportWarningsModal({ warnings, onClose }: Props) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Export Blocked — Fix Before PDF</h2>
          <button className="modal-x" onClick={onClose} title="Close">×</button>
        </div>
        <div className="modal-body">
          <p className="cw-note">
            PDF export is blocked until these issues are resolved. Each row lists the page, the problem, and a suggested fix.
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
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
