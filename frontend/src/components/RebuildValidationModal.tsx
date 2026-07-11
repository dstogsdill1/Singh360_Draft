interface Props {
  issues: string[];
  onKeepCurrent: () => void;
  onReplaceAnyway: () => void;
}

export default function RebuildValidationModal({ issues, onKeepCurrent, onReplaceAnyway }: Props) {
  return (
    <div className="modal-backdrop" onClick={onKeepCurrent}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Rebuild Failed Validation</h2>
          <button className="modal-x" onClick={onKeepCurrent} title="Close">×</button>
        </div>
        <div className="modal-body">
          <p className="cw-note">
            The rebuilt page did not pass quality checks. Your current normalized page was kept.
            Review the issues below, then choose whether to keep the current page or replace anyway.
          </p>
          <ul className="rebuild-validation-list">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={onKeepCurrent}>Keep Current Page</button>
          <button className="btn" onClick={onReplaceAnyway}>Replace Anyway</button>
        </div>
      </div>
    </div>
  );
}
