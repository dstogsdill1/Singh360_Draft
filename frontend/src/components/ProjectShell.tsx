import { useRef, useState, type ReactNode } from 'react';

interface Props {
  ribbon: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  status?: ReactNode;
}

type Side = 'left' | 'right';
const HOVER_OPEN_DELAY_MS = 1000;
const HOVER_CLOSE_DELAY_MS = 280;

function savedPin(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

export default function ProjectShell({ ribbon, left, center, right, status }: Props) {
  const [leftPinned, setLeftPinned] = useState(() => savedPin('singh360-panel-left-pinned'));
  const [rightPinned, setRightPinned] = useState(() => savedPin('singh360-panel-right-pinned'));
  const [leftHover, setLeftHover] = useState(false);
  const [rightHover, setRightHover] = useState(false);
  const openTimers = useRef<Record<Side, number | null>>({ left: null, right: null });
  const closeTimers = useRef<Record<Side, number | null>>({ left: null, right: null });

  const leftOpen = leftPinned || leftHover;
  const rightOpen = rightPinned || rightHover;

  const clearOpenTimer = (side: Side) => {
    const timer = openTimers.current[side];
    if (timer != null) window.clearTimeout(timer);
    openTimers.current[side] = null;
  };

  const clearCloseTimer = (side: Side) => {
    const timer = closeTimers.current[side];
    if (timer != null) window.clearTimeout(timer);
    closeTimers.current[side] = null;
  };

  const scheduleOpen = (side: Side) => {
    const pinned = side === 'left' ? leftPinned : rightPinned;
    if (pinned) return;
    clearOpenTimer(side);
    clearCloseTimer(side);
    openTimers.current[side] = window.setTimeout(() => {
      if (side === 'left') setLeftHover(true);
      else setRightHover(true);
      openTimers.current[side] = null;
    }, HOVER_OPEN_DELAY_MS);
  };

  const keepOpen = (side: Side) => {
    clearOpenTimer(side);
    clearCloseTimer(side);
  };

  const scheduleClose = (side: Side) => {
    const pinned = side === 'left' ? leftPinned : rightPinned;
    if (pinned) return;
    clearOpenTimer(side);
    clearCloseTimer(side);
    closeTimers.current[side] = window.setTimeout(() => {
      if (side === 'left') setLeftHover(false);
      else setRightHover(false);
      closeTimers.current[side] = null;
    }, HOVER_CLOSE_DELAY_MS);
  };

  const setPinned = (side: Side, value: boolean) => {
    clearOpenTimer(side);
    clearCloseTimer(side);
    try {
      localStorage.setItem(`singh360-panel-${side}-pinned`, value ? '1' : '0');
    } catch {
      /* ignore unavailable storage */
    }
    if (side === 'left') {
      setLeftPinned(value);
      setLeftHover(false);
    } else {
      setRightPinned(value);
      setRightHover(false);
    }
  };

  const bodyClass = `app-body ${leftOpen ? '' : 'left-collapsed'} ${rightOpen ? '' : 'right-collapsed'}`.trim();

  return (
    <div className="app-shell">
      {ribbon}
      <div className={bodyClass}>
        {leftOpen ? (
          <aside
            className={`panel-left ${leftPinned ? 'is-pinned' : 'is-hover-panel'}`}
            onMouseEnter={() => keepOpen('left')}
            onMouseLeave={() => scheduleClose('left')}
          >
            <div className="panel-collapse-bar">
              <span>Navigation</span>
              <span className="panel-bar-actions">
                <button
                  className={`panel-pin-btn ${leftPinned ? 'active' : ''}`}
                  title={leftPinned ? 'Unpin navigation panel' : 'Pin navigation panel open'}
                  onClick={() => setPinned('left', !leftPinned)}
                >
                  {leftPinned ? 'Pinned' : 'Pin'}
                </button>
                <button className="panel-collapse-btn" title="Hide navigation" onClick={() => setPinned('left', false)}>‹</button>
              </span>
            </div>
            {left}
          </aside>
        ) : (
          <button
            className="panel-rail panel-rail-left"
            title="Hover for one second, or click to pin navigation open"
            onMouseEnter={() => scheduleOpen('left')}
            onMouseLeave={() => clearOpenTimer('left')}
            onFocus={() => scheduleOpen('left')}
            onBlur={() => clearOpenTimer('left')}
            onClick={() => setPinned('left', true)}
          >
            <span className="rail-icon">☰</span>
            <span className="rail-label">Navigate</span>
          </button>
        )}

        <section className="editor-center">{center}</section>

        {rightOpen ? (
          <aside
            className={`panel-right ${rightPinned ? 'is-pinned' : 'is-hover-panel'}`}
            onMouseEnter={() => keepOpen('right')}
            onMouseLeave={() => scheduleClose('right')}
          >
            <div className="panel-collapse-bar">
              <span>Properties</span>
              <span className="panel-bar-actions">
                <button
                  className={`panel-pin-btn ${rightPinned ? 'active' : ''}`}
                  title={rightPinned ? 'Unpin properties panel' : 'Pin properties panel open'}
                  onClick={() => setPinned('right', !rightPinned)}
                >
                  {rightPinned ? 'Pinned' : 'Pin'}
                </button>
                <button className="panel-collapse-btn" title="Hide properties" onClick={() => setPinned('right', false)}>›</button>
              </span>
            </div>
            {right}
          </aside>
        ) : (
          <button
            className="panel-rail panel-rail-right"
            title="Hover for one second, or click to pin properties open"
            onMouseEnter={() => scheduleOpen('right')}
            onMouseLeave={() => clearOpenTimer('right')}
            onFocus={() => scheduleOpen('right')}
            onBlur={() => clearOpenTimer('right')}
            onClick={() => setPinned('right', true)}
          >
            <span className="rail-icon">⚙</span>
            <span className="rail-label">Properties</span>
          </button>
        )}
      </div>
      {status ?? <div className="status-bar" />}
    </div>
  );
}
