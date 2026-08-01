import type { PageModel } from './types';

const clean = (value: unknown) => String(value ?? '').trim();

/** Suggest the next code from the user's current drawing sequence.
 *
 * The helper never invents a prefix. It increments the nearest real code,
 * retains zero padding, and skips codes already in use. Decimal drawing codes
 * advance their final numeric segment (EMS 3.0 -> EMS 3.1).
 */
export function nextLogicalSheetCode(pages: PageModel[], anchorPageId?: string): string {
  const ordered = [...(pages ?? [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const candidates = ordered.filter((page) => (
    page.managedPage !== 'cover'
    && page.managedPage !== 'index'
    && page.pageType !== 'cover'
    && page.pageType !== 'index'
    && !page.continuationOf
    && !page.generatedContinuation
    && !/^new$/i.test(clean(page.displaySheetCode || page.sheetCode))
    && !!clean(page.displaySheetCode || page.sheetCode)
  ));
  const anchor = candidates.find((page) => page.id === anchorPageId) ?? candidates[candidates.length - 1];
  const current = clean(anchor?.displaySheetCode || anchor?.sheetCode);
  const match = current.match(/^(.*?)(\d+)(?:\.(\d+))?$/);
  if (!match) return '';

  const used = new Set(ordered.map((page) => clean(page.displaySheetCode || page.sheetCode).toLowerCase()).filter(Boolean));
  const prefix = match[1];
  const whole = match[2];
  const fraction = match[3];
  let increment = Number(fraction ?? whole) + 1;
  for (let attempt = 0; attempt < 10_000; attempt += 1, increment += 1) {
    const nextNumber = String(increment).padStart((fraction ?? whole).length, '0');
    const suggestion = fraction === undefined
      ? `${prefix}${nextNumber}`
      : `${prefix}${whole}.${nextNumber}`;
    if (!used.has(suggestion.toLowerCase())) return suggestion;
  }
  return '';
}
