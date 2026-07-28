import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getTooltipDefinition, tooltipScopeLabel, type TooltipDefinition } from './tooltipRegistry';

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right';

export type ActiveTooltip = {
  target: HTMLElement;
  helpId: string;
  definition: TooltipDefinition;
  openedBy: 'hover' | 'focus';
};

const TOOLTIP_ID = 's360-app-tooltip';
const GAP = 10;
const VIEWPORT_PAD = 8;

function placementOrder(target: HTMLElement): TooltipPlacement[] {
  const preferred = target.dataset.tooltipPlacement as TooltipPlacement | undefined;
  const defaults: TooltipPlacement[] = ['bottom', 'top', 'right', 'left'];
  return preferred && defaults.includes(preferred)
    ? [preferred, ...defaults.filter((value) => value !== preferred)]
    : defaults;
}

function positionFor(
  placement: TooltipPlacement,
  target: DOMRect,
  tooltip: DOMRect,
): { left: number; top: number; fits: boolean } {
  let left = target.left + (target.width - tooltip.width) / 2;
  let top = target.bottom + GAP;
  if (placement === 'top') top = target.top - tooltip.height - GAP;
  if (placement === 'left') {
    left = target.left - tooltip.width - GAP;
    top = target.top + (target.height - tooltip.height) / 2;
  }
  if (placement === 'right') {
    left = target.right + GAP;
    top = target.top + (target.height - tooltip.height) / 2;
  }
  const fits = left >= VIEWPORT_PAD
    && top >= VIEWPORT_PAD
    && left + tooltip.width <= window.innerWidth - VIEWPORT_PAD
    && top + tooltip.height <= window.innerHeight - VIEWPORT_PAD;
  return { left, top, fits };
}

function disabledExplanation(active: ActiveTooltip): string {
  const { target, definition } = active;
  if (!(target.matches(':disabled') || target.getAttribute('aria-disabled') === 'true')) return '';
  const explicit = target.dataset.disabledReason?.trim();
  if (explicit) return explicit;
  if (typeof definition.disabledReason === 'function') {
    return definition.disabledReason({ disabled: true, disabledReason: explicit });
  }
  if (definition.disabledReason) return definition.disabledReason;
  if (!target.closest('[data-project-loaded="true"]') && /project|save|export|page/i.test(definition.title)) {
    return 'Open a Singh360 project to enable this command.';
  }
  return 'This command needs the required project, selection, or linked resource before it can run.';
}

export default function AppTooltip({
  active,
  viewportTick,
}: {
  active: ActiveTooltip | null;
  viewportTick: number;
}) {
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: -9999, top: -9999, placement: 'bottom' as TooltipPlacement });

  useLayoutEffect(() => {
    if (!active || !tooltipRef.current || !document.contains(active.target)) return;
    const targetRect = active.target.getBoundingClientRect();
    const tooltipRect = tooltipRef.current.getBoundingClientRect();
    const candidates = placementOrder(active.target);
    let selected = { ...positionFor(candidates[0], targetRect, tooltipRect), placement: candidates[0] };
    for (const placement of candidates) {
      const candidate = { ...positionFor(placement, targetRect, tooltipRect), placement };
      selected = candidate;
      if (candidate.fits) break;
    }
    setPosition({
      placement: selected.placement,
      left: Math.min(
        Math.max(VIEWPORT_PAD, selected.left),
        Math.max(VIEWPORT_PAD, window.innerWidth - tooltipRect.width - VIEWPORT_PAD),
      ),
      top: Math.min(
        Math.max(VIEWPORT_PAD, selected.top),
        Math.max(VIEWPORT_PAD, window.innerHeight - tooltipRect.height - VIEWPORT_PAD),
      ),
    });
  // Recalculate only when the active target or an explicit viewport tick changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, viewportTick]);

  if (!active) return null;
  const disabledReason = disabledExplanation(active);
  const dynamicBody = active.target.dataset.tooltipBody?.trim();
  const body = dynamicBody || active.definition.body;

  return createPortal(
    <div
      ref={tooltipRef}
      id={TOOLTIP_ID}
      className={`s360-app-tooltip placement-${position.placement}`}
      role="tooltip"
      data-help-id={active.helpId}
      data-opened-by={active.openedBy}
      style={{ left: position.left, top: position.top }}
    >
      <div className="s360-app-tooltip-arrow" aria-hidden="true" />
      <strong>{active.definition.title}</strong>
      <span>{body}</span>
      {disabledReason && <span className="s360-app-tooltip-disabled">Unavailable: {disabledReason}</span>}
      <small>{tooltipScopeLabel(active.definition.saveScope)}</small>
      {active.definition.shortcut && <kbd>{active.definition.shortcut}</kbd>}
    </div>,
    document.body,
  );
}

export function openTooltipFor(target: HTMLElement, openedBy: ActiveTooltip['openedBy']): ActiveTooltip | null {
  const helpId = target.dataset.helpId || '';
  const definition = getTooltipDefinition(helpId);
  return definition ? { target, helpId, definition, openedBy } : null;
}

export const APP_TOOLTIP_ID = TOOLTIP_ID;
