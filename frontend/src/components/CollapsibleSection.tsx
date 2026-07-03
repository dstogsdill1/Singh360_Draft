import { useState, type ReactNode } from 'react';

interface Props {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}

export default function CollapsibleSection({ title, children, defaultOpen = true }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`nav-section ${open ? 'expanded' : 'collapsed'}`}>
      <div className="nav-section-head" onClick={() => setOpen((o) => !o)}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        {title}
      </div>
      {open && <div className="nav-section-body">{children}</div>}
    </div>
  );
}
