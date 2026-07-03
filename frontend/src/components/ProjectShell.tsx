import { useState, type ReactNode } from 'react';

interface Props {
  ribbon: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  status?: ReactNode;
}

export default function ProjectShell({ ribbon, left, center, right, status }: Props) {
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  const bodyClass = `app-body ${leftOpen ? '' : 'left-collapsed'} ${rightOpen ? '' : 'right-collapsed'}`.trim();

  return (
    <div className="app-shell">
      {ribbon}
      <div className={bodyClass}>
        {leftOpen ? (
          <aside className="panel-left">
            <div className="panel-collapse-bar">
              <span>Pages</span>
              <button className="panel-collapse-btn" title="Collapse" onClick={() => setLeftOpen(false)}>‹</button>
            </div>
            {left}
          </aside>
        ) : (
          <button className="panel-rail panel-rail-left" title="Expand Pages" onClick={() => setLeftOpen(true)}>
            <span className="rail-label">Pages</span>
          </button>
        )}

        <section className="editor-center">{center}</section>

        {rightOpen ? (
          <aside className="panel-right">
            <div className="panel-collapse-bar">
              <span>Properties</span>
              <button className="panel-collapse-btn" title="Collapse" onClick={() => setRightOpen(false)}>›</button>
            </div>
            {right}
          </aside>
        ) : (
          <button className="panel-rail panel-rail-right" title="Expand Properties" onClick={() => setRightOpen(true)}>
            <span className="rail-label">Properties</span>
          </button>
        )}
      </div>
      {status ?? <div className="status-bar" />}
    </div>
  );
}
