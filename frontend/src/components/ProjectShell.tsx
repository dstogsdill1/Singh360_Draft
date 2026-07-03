import type { ReactNode } from 'react';

interface Props {
  ribbon: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  status?: ReactNode;
}

export default function ProjectShell({ ribbon, left, center, right, status }: Props) {
  return (
    <div className="app-shell">
      {ribbon}
      <div className="app-body">
        <aside className="panel-left">{left}</aside>
        <section className="editor-center">{center}</section>
        <aside className="panel-right">{right}</aside>
      </div>
      {status ?? <div className="status-bar" />}
    </div>
  );
}
