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
      <button type="button" className="nav-section-head" onClick={() => setOpen((o) => !o)} title={hint || title} aria-expanded={open}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        <span className="nav-section-title-block">
          <span className="nav-section-title">{title}</span>
          {open && hint ? <span className="nav-section-caption">{hint}</span> : null}
        </span>
      </button>
      {open && <div className="nav-section-body">{children}</div>}
    </div>
  );
}
