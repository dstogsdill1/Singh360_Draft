import { useLayoutEffect, useRef } from 'react';

interface MenuAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  hint?: string;
  divider?: boolean;
}

interface Props {
  x: number;
  y: number;
  actions: MenuAction[];
  onClose: () => void;
}

/** App-level right-click menu for the sheet body (PowerPoint/Visio style). */
export default function SheetContextMenu({ x, y, actions, onClose }: Props) {
  const menuRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const m = menuRef.current;
    if (!m) return;
    const PAD = 8;
    const w = m.offsetWidth || 220;
    const h = m.offsetHeight || 220;
    const maxLeft = Math.max(PAD, window.innerWidth - w - PAD);
    const maxTop = Math.max(PAD, window.innerHeight - h - PAD);
    const left = Math.min(Math.max(x, PAD), maxLeft);
    const top = Math.min(Math.max(y, PAD), maxTop);
    m.style.left = `${left}px`;
    m.style.top = `${top}px`;
  }, [x, y, actions.length]);

  return (
    <div className="ctx-backdrop" onClick={onClose} onContextMenu={(e) => { e.preventDefault(); onClose(); }}>
      <div ref={menuRef} className="ctx-menu" onClick={(e) => e.stopPropagation()}>
        {actions.map((a, i) => (
          <div key={i}>
            {a.divider && <div className="ctx-divider" />}
            <button
              className="ctx-item"
              disabled={a.disabled}
              title={a.hint}
              onClick={() => {
                if (!a.disabled) {
                  a.onClick();
                  onClose();
                }
              }}
            >
              {a.label}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
