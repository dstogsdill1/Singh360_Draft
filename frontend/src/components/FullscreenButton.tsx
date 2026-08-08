import { useCallback } from 'react';
import { useFullscreen } from '../hooks/useFullscreen';

export default function FullscreenButton() {
  const getAppShell = useCallback(
    () => document.querySelector<HTMLElement>('.app-shell'),
    [],
  );
  const fullscreen = useFullscreen(getAppShell);
  const label = fullscreen.isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen';

  return (
    <span className="fullscreen-control" data-noexport>
      <button
        type="button"
        className={`ribbon-btn fullscreen-toggle ${fullscreen.isFullscreen ? 'active' : ''}`}
        data-testid="fullscreen-toggle"
        aria-label={label}
        title={label}
        disabled={!fullscreen.isSupported}
        onClick={() => { void fullscreen.toggle(); }}
      >
        <span aria-hidden="true">{fullscreen.isFullscreen ? '🗗' : '⛶'}</span>
      </button>
      {fullscreen.error ? (
        <span className="fullscreen-error" role="status" aria-live="polite">
          {fullscreen.error}
        </span>
      ) : null}
    </span>
  );
}
