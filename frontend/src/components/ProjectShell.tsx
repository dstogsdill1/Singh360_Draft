import { useRef, useState, type ReactNode } from 'react';

interface Props {
  ribbon: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  status?: ReactNode;
}

type Side = 'left' | 'right';

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
  const timers = useRef<Record<Side, number | null>>({ left: null, right: null });

  const leftOpen = leftPinned || leftHover;
  const rightOpen = rightPinned || rightHover;

  const cancelClose = (side: Side) => {
    const timer = timers.current[side];
    if (timer != null) window.clearTimeout(timer);
    timers.current[side] = null;
    if (side === 'left') setLeftHover(true);
    else setRightHover(true);
  };

  const scheduleClose = (side: Side) => {
    const pinned = side === 'left' ? leftPinned : rightPinned;
    if (pinned) return;
    const timer = timers.current[side];
    if (timer != null) window.clearTimeout(timer);
    timers.current[side] = window.setTimeout(() => {
      if (side === 'left') setLeftHover(false);
      else setRightHover(false);
      timers.current[side] = null;
    }, 260);
  };

  const setPinned = (side: Side, value: boolean) => {
    try { localStorage.setItem(`singh360-panel-${side}-pinned`, value ? '1' : '0'); } catch { /* ignore */ }
    if (side === 'left') {
      setLeftPinned(value);
      if (!value) setLeftHover(false);
    } else {
      setRightPinned(value);
      if (!value) setRightHover(false);
    }
  };

  const bodyClass = `app-body ${leftOpen ? '' : 'left-collapsed'} ${rightOpen ? '' : 'right-collapsed'}`.trim();

  return (
    <div className="app-shell">
      {ribbon}
      <div className={bodyClass}>
        {leftOpen ? (
          <aside className={`panel-left ${leftPinned ? 'is-pinned' : 'is-hover-panel'}`} onMouseEnter={() => cancelClose('left')} onMouseLeave={() => scheduleClose('left')}>
            <div className="panel-collapse-bar">
              <span>Navigation</span>
              <span className="panel-bar-actions">
                <button className={`panel-pin-btn ${leftPinned ? 'active' : ''}`} title={leftPinned ? 'Unpin navigation panel' : 'Pin navigation panel open'} onClick={() => setPinned('left', !leftPinned)}>{leftPinned ? 'Pinned' : 'Pin'}</button>
                <button className="panel-collapse-btn" title="Hide navigation" onClick={() => setPinned('left', false)}>‹</button>
              </span>
            </div>
            {left}
          </aside>
        ) : (
          <button className="panel-rail panel-rail-left" title="Hover to open navigation" onMouseEnter={() => cancelClose('left')} onFocus={() => cancelClose('left')} onClick={() => setPinned('left', true)}>
            <span className="rail-icon">☰</span>
            <span className="rail-label">Navigate</span>
          </button>
        )}

        <section className="editor-center">{center}</section>

        {rightOpen ? (
          <aside className={`panel-right ${rightPinned ? 'is-pinned' : 'is-hover-panel'}`} onMouseEnter={() => cancelClose('right')} onMouseLeave={() => scheduleClose('right')}>
            <div className="panel-collapse-bar">
              <span>Properties</span>
              <span className="panel-bar-actions">
                <button className={`panel-pin-btn ${rightPinned ? 'active' : ''}`} title={rightPinned ? 'Unpin properties panel' : 'Pin properties panel open'} onClick={() => setPinned('right', !rightPinned)}>{rightPinned ? 'Pinned' : 'Pin'}</button>
                <button className="panel-collapse-btn" title="Hide properties" onClick={() => setPinned('right', false)}>›</button>
              </span>
            </div>
            {right}
          </aside>
        ) : (
          <button className="panel-rail panel-rail-right" title="Hover to open properties" onMouseEnter={() => cancelClose('right')} onFocus={() => cancelClose('right')} onClick={() => setPinned('right', true)}>
            <span className="rail-icon">⚙</span>
            <span className="rail-label">Properties</span>
          </button>
        )}
      </div>
      {status ?? <div className="status-bar" />}
    </div>
  );
}
