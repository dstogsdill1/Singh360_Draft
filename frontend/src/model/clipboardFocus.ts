const CLIPBOARD_EDITOR_SELECTOR = [
  'input',
  'textarea',
  'select',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="textbox"]',
  '[role="dialog"]',
  '[data-clipboard-editor="true"]',
].join(',');

function matchesEditingContext(value: EventTarget | Element | null): boolean {
  if (!(value instanceof Element)) return false;
  return value.matches(CLIPBOARD_EDITOR_SELECTOR)
    || Boolean(value.closest(CLIPBOARD_EDITOR_SELECTOR));
}

/**
 * Canvas clipboard shortcuts must stand down anywhere the user can type, and
 * throughout an open editor dialog even when a button currently has focus.
 */
export function isClipboardEditingContext(target: EventTarget | null): boolean {
  return matchesEditingContext(target)
    || matchesEditingContext(document.activeElement);
}
