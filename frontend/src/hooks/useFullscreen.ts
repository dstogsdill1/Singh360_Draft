import { useCallback, useEffect, useState } from 'react';

type FullscreenTarget = () => HTMLElement | null;

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return 'The browser did not allow fullscreen mode.';
}

/** Browser Fullscreen API state for one stable app-shell element. */
export function useFullscreen(getTarget: FullscreenTarget) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isSupported, setIsSupported] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const syncState = () => {
      const target = getTarget();
      setIsFullscreen(Boolean(target && document.fullscreenElement === target));
      setIsSupported(Boolean(
        document.fullscreenEnabled
        && target
        && typeof target.requestFullscreen === 'function'
        && typeof document.exitFullscreen === 'function'
      ));
    };
    const reportError = () => {
      setError('The browser rejected fullscreen mode. The drawing remains unchanged.');
      syncState();
    };

    syncState();
    document.addEventListener('fullscreenchange', syncState);
    document.addEventListener('fullscreenerror', reportError);
    return () => {
      document.removeEventListener('fullscreenchange', syncState);
      document.removeEventListener('fullscreenerror', reportError);
    };
  }, [getTarget]);

  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(''), 6000);
    return () => window.clearTimeout(timer);
  }, [error]);

  const toggle = useCallback(async () => {
    setError('');
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }
      const target = getTarget();
      if (
        !document.fullscreenEnabled
        || !target
        || typeof target.requestFullscreen !== 'function'
      ) {
        setIsSupported(false);
        setError('Fullscreen is unavailable in this browser. The drawing remains unchanged.');
        return;
      }
      // This call remains inside the button's click handler so browser user-
      // activation requirements are preserved.
      await target.requestFullscreen();
    } catch (caught) {
      setError(`${errorMessage(caught)} The drawing remains unchanged.`);
    }
  }, [getTarget]);

  return {
    error,
    isFullscreen,
    isSupported,
    toggle,
  };
}
