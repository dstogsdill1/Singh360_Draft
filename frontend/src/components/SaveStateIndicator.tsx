import { useState } from 'react';
import {
  SAVE_STATE_LABELS,
  saveStateHelpId,
  type DirtyDomain,
  type SaveState,
} from '../model/saveState';

export default function SaveStateIndicator({
  state,
  lastLocalSave,
  lastWorkbookSync,
  dirtyDomains,
  error,
  onRetry,
  labelOverride,
}: {
  state: SaveState;
  lastLocalSave?: string;
  lastWorkbookSync?: string;
  dirtyDomains: DirtyDomain[];
  error?: string;
  onRetry: () => void;
  labelOverride?: string;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const dirty = state === 'dirtyLocal' || state === 'dirtyWorkspace' || state === 'saveFailed';
  const helpId = saveStateHelpId(state);

  return (
    <div className="save-state-control">
      <button
        type="button"
        className={`status-pill ${state}`}
        data-help-id={helpId}
        data-status-chip="true"
        onClick={state === 'saveFailed' ? onRetry : () => setDetailsOpen((value) => !value)}
        aria-expanded={detailsOpen}
      >
        {labelOverride || SAVE_STATE_LABELS[state]}
      </button>
      <div className="save-state-times">
        {lastLocalSave && (
          <span data-help-id="status.lastLocalSave" data-status-chip="true">
            Last local save: {lastLocalSave}
          </span>
        )}
        {lastWorkbookSync && (
          <span data-help-id="status.lastWorkbookSync" data-status-chip="true">
            Last workbook sync: {lastWorkbookSync}
          </span>
        )}
      </div>
      {(dirty || detailsOpen) && (
        <button
          type="button"
          className="save-state-details-button"
          data-help-id="status.whatUnsaved"
          onClick={() => setDetailsOpen((value) => !value)}
        >
          What is unsaved?
        </button>
      )}
      {error && <span className="save-state-error" role="alert">{error}</span>}
      {detailsOpen && (
        <section className="save-state-details" role="dialog" aria-label="Unsaved change details">
          <strong>{dirtyDomains.length ? 'Waiting for local save' : 'No unconfirmed local edits'}</strong>
          {dirtyDomains.length > 0 && (
            <ul>{dirtyDomains.map((domain) => <li key={domain}>{domain}</li>)}</ul>
          )}
          {state === 'saveFailed' && (
            <button type="button" data-help-id="save.retry" onClick={onRetry}>Retry save</button>
          )}
        </section>
      )}
    </div>
  );
}
