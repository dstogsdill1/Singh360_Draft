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
  return (
    <div className="ctx-backdrop" onClick={onClose} onContextMenu={(e) => { e.preventDefault(); onClose(); }}>
      <div className="ctx-menu" style={{ left: x, top: y }} onClick={(e) => e.stopPropagation()}>
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
