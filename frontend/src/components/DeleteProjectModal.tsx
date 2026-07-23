import { useState, type ChangeEvent } from 'react';

interface Props {
  projectName: string;
  busy?: boolean;
  onClose: () => void;
  onDelete: () => Promise<void>;
}

export default function DeleteProjectModal({ projectName, busy, onClose, onDelete }: Props) {
  const [confirmation, setConfirmation] = useState('');
  const matches = confirmation.trim() === projectName.trim();
  return (
    <div className="dashboard-overlay" role="dialog" aria-modal="true">
      <div className="delete-project-modal">
        <h2>Remove Project</h2>
        <p>This moves the selected Singh360 project package into the Singh360 archive and removes it from the active project list. It does not delete the external G:/Drive workbook.</p>
        <div className="delete-safety">
          <strong>Project to remove</strong>
          <code>{projectName}</code>
        </div>
        <label>
          Type the exact project name to enable removal:
          <input value={confirmation} onChange={(event: ChangeEvent<HTMLInputElement>) => setConfirmation(event.target.value)} />
        </label>
        <div>
          <button type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="danger" disabled={busy || !matches} onClick={() => void onDelete()}>Remove This Project</button>
        </div>
      </div>
    </div>
  );
}
