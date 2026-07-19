import { useLayoutEffect, useRef } from 'react';
import {
  copyActiveCanvasToSystemClipboard,
  pasteSystemClipboardToActiveCanvas,
} from '../clipboardBridge';

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
    const menu = menuRef.current;
    if (!menu) return;
    const padding = 8;
    const width = menu.offsetWidth || 220;
    const height = menu.offsetHeight || 220;
    const maxLeft = Math.max(padding, window.innerWidth - width - padding);
    const maxTop = Math.max(padding, window.innerHeight - height - padding);
    const left = Math.min(Math.max(x, padding), maxLeft);
    const top = Math.min(Math.max(y, padding), maxTop);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  }, [x, y, actions.length]);

  const runAction = async (action: MenuAction) => {
    if (action.disabled) return;

    if (action.label === 'Copy') {
      const copied = await copyActiveCanvasToSystemClipboard();
      if (!copied) action.onClick();
      onClose();
      return;
    }

    if (action.label === 'Paste') {
      const pasted = await pasteSystemClipboardToActiveCanvas();
      if (!pasted) action.onClick();
      onClose();
      return;
    }

    action.onClick();
    onClose();
  };

  return (
    <div
      className="ctx-backdrop"
      onClick={onClose}
      onContextMenu={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div ref={menuRef} className="ctx-menu" onClick={(e) => e.stopPropagation()}>
        {actions.map((action, index) => (
          <div key={index}>
            {action.divider && <div className="ctx-divider" />}
            <button
              className="ctx-item"
              disabled={action.disabled}
              title={action.hint}
              onClick={() => void runAction(action)}
            >
              {action.label}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
