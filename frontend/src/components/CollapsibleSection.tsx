import { useState, type ReactNode } from 'react';

interface Props {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  hint?: string;
}

export default function CollapsibleSection({ title, children, defaultOpen = true, hint }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`nav-section ${open ? 'expanded' : 'collapsed'}`}>
      <div className="nav-section-head" onClick={() => setOpen((o) => !o)} title={hint || title}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        {title}
      </div>
      {open && <div className="nav-section-body">{children}</div>}
    </div>
  );
}
