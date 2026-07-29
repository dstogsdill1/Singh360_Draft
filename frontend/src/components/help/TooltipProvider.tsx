import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import AppTooltip, { APP_TOOLTIP_ID, openTooltipFor, type ActiveTooltip } from './AppTooltip';
import {
  hydrateTooltipTargets,
  runTooltipAudit,
  validateTooltipRegistry,
} from './TooltipAudit';

const HOVER_DELAY_MS = 650;
const LEAVE_GRACE_MS = 140;

function modalIsOpen(): boolean {
  return Boolean(document.querySelector(
    'dialog[open], [role="dialog"][aria-modal="true"], [role="alertdialog"][aria-modal="true"]',
  ));
}

function withDescription(target: HTMLElement): void {
  const ids = new Set((target.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
  ids.add(APP_TOOLTIP_ID);
  target.setAttribute('aria-describedby', [...ids].join(' '));
}

function withoutDescription(target: HTMLElement): void {
  const ids = (target.getAttribute('aria-describedby') || '')
    .split(/\s+/)
    .filter((id) => id && id !== APP_TOOLTIP_ID);
  if (ids.length) target.setAttribute('aria-describedby', ids.join(' '));
  else target.removeAttribute('aria-describedby');
}

function tooltipTarget(value: EventTarget | null): HTMLElement | null {
  if (!(value instanceof Element)) return null;
  return value.closest<HTMLElement>('[data-help-id]');
}

export default function TooltipProvider({ children }: { children: ReactNode }) {
  const [active, setActiveState] = useState<ActiveTooltip | null>(null);
  const [viewportTick, setViewportTick] = useState(0);
  const activeRef = useRef<ActiveTooltip | null>(null);
  const hoverTimerRef = useRef<number | null>(null);
  const leaveTimerRef = useRef<number | null>(null);

  const clearTimers = useCallback(() => {
    if (hoverTimerRef.current !== null) window.clearTimeout(hoverTimerRef.current);
    if (leaveTimerRef.current !== null) window.clearTimeout(leaveTimerRef.current);
    hoverTimerRef.current = null;
    leaveTimerRef.current = null;
  }, []);

  const setActive = useCallback((next: ActiveTooltip | null) => {
    if (activeRef.current?.target && activeRef.current.target !== next?.target) {
      withoutDescription(activeRef.current.target);
    }
    activeRef.current = next;
    if (next) withDescription(next.target);
    setActiveState(next);
  }, []);

  const close = useCallback(() => {
    clearTimers();
    if (activeRef.current?.target) withoutDescription(activeRef.current.target);
    activeRef.current = null;
    setActiveState(null);
  }, [clearTimers]);

  useEffect(() => {
    hydrateTooltipTargets();
    const registryErrors = validateTooltipRegistry();
    if (registryErrors.length) console.error('Singh360 tooltip registry errors', registryErrors);

    const observer = new MutationObserver((mutations) => {
      if (modalIsOpen()) close();
      mutations.forEach((mutation) => {
        if (mutation.type === 'attributes' && mutation.target instanceof HTMLElement) {
          hydrateTooltipTargets(mutation.target);
        }
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof HTMLElement)) return;
          hydrateTooltipTargets(node);
        });
      });
    });
    observer.observe(document.getElementById('root') || document.body, {
      attributes: true,
      attributeFilter: ['title', 'open', 'aria-modal'],
      childList: true,
      subtree: true,
    });

    const onMouseOver = (event: MouseEvent) => {
      if (modalIsOpen()) {
        close();
        return;
      }
      const target = tooltipTarget(event.target);
      if (!target) return;
      if (leaveTimerRef.current !== null) window.clearTimeout(leaveTimerRef.current);
      if (activeRef.current?.target === target) return;
      if (hoverTimerRef.current !== null) window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = window.setTimeout(() => {
        if (modalIsOpen()) {
          close();
          return;
        }
        setActive(openTooltipFor(target, 'hover'));
        hoverTimerRef.current = null;
      }, HOVER_DELAY_MS);
    };

    const onMouseOut = (event: MouseEvent) => {
      const target = tooltipTarget(event.target);
      if (!target) return;
      if (event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) return;
      if (hoverTimerRef.current !== null) {
        window.clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
      if (activeRef.current?.target !== target || activeRef.current.openedBy === 'focus') return;
      leaveTimerRef.current = window.setTimeout(close, LEAVE_GRACE_MS);
    };

    const onFocusIn = (event: FocusEvent) => {
      if (modalIsOpen()) {
        close();
        return;
      }
      const target = tooltipTarget(event.target);
      if (!target) return;
      clearTimers();
      setActive(openTooltipFor(target, 'focus'));
    };

    const onFocusOut = (event: FocusEvent) => {
      const target = tooltipTarget(event.target);
      if (!target || activeRef.current?.target !== target) return;
      if (event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) return;
      close();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && activeRef.current) {
        event.stopPropagation();
        close();
      }
    };

    const onViewportChange = () => setViewportTick((value) => value + 1);
    document.addEventListener('mouseover', onMouseOver, true);
    document.addEventListener('mouseout', onMouseOut, true);
    document.addEventListener('focusin', onFocusIn, true);
    document.addEventListener('focusout', onFocusOut, true);
    document.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('scroll', onViewportChange, true);

    const auditEnabled = window.location.port !== '8766'
      || new URLSearchParams(window.location.search).get('tooltipAudit') === '1';
    if (auditEnabled) window.__S360_TOOLTIP_AUDIT__ = () => runTooltipAudit();

    return () => {
      observer.disconnect();
      document.removeEventListener('mouseover', onMouseOver, true);
      document.removeEventListener('mouseout', onMouseOut, true);
      document.removeEventListener('focusin', onFocusIn, true);
      document.removeEventListener('focusout', onFocusOut, true);
      document.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('scroll', onViewportChange, true);
      delete window.__S360_TOOLTIP_AUDIT__;
      close();
    };
  }, [clearTimers, close, setActive]);

  return (
    <>
      {children}
      <AppTooltip active={active} viewportTick={viewportTick} />
    </>
  );
}
