import type { ReactNode } from 'react';

interface Props {
  toolbar: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
}

export default function ProjectShell({ toolbar, left, center, right }: Props) {
  return (
    <div className="app-shell">
      <div className="toolbar">{toolbar}</div>
      <aside className="panel-left">{left}</aside>
      <main className="panel-center">{center}</main>
      <aside className="panel-right">{right}</aside>
    </div>
  );
}
