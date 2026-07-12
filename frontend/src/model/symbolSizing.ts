/** Standard on-canvas symbol sizes (px) — Phase C symbol sizing. */

export const SYMBOL_SIZE_SMALL = 18;
export const SYMBOL_SIZE_SIGNAGE = 22;
export const SYMBOL_SIZE_EQUIPMENT = 34;
export const SYMBOL_SIZE_LARGE = 80;

const SMALL_ACRONYMS = new Set([
  'LI', 'DA', 'LS', 'ES', 'EA', 'HS',
  'T', 'TS', 'DS', 'DTS', 'OAT', 'LT', 'NC', 'NO', 'DI',
  'EEV', 'LLS', 'EEPR', 'EPR', 'DEF', 'AS/TRIM',
]);

const EQUIPMENT_TERMS = [
  'wicp', 'lcp', 'rdm idf', 'mdf', 'rdm data manager', 'data manager', 'orbit touch',
  'powerscout', 'power monitor', 'refrigeration rack', 'evaporator fan',
  'condenser fan', 'evaporator coil', 'compressor',
];

const SIGNAGE_TERMS = [
  'person trapped', 'leak do not enter', 'help trapped', 'when lit',
];

export interface SymbolSizeHints {
  category?: string;
  acronym?: string;
  name?: string;
  defaultWidth?: number;
  defaultHeight?: number;
}

export function standardSymbolSize(hints: SymbolSizeHints): { w: number; h: number } {
  const dw = hints.defaultWidth;
  const dh = hints.defaultHeight;
  if (dw && dh && dw > 0 && dh > 0) {
    return { w: dw, h: dh };
  }

  const cat = (hints.category || '').toLowerCase();
  const name = `${hints.name || ''} ${hints.acronym || ''}`.toLowerCase();
  const acr = (hints.acronym || '').trim();

  if (SIGNAGE_TERMS.some((t) => name.includes(t))) {
    return { w: SYMBOL_SIZE_SIGNAGE, h: SYMBOL_SIZE_SIGNAGE };
  }
  if (acr && SMALL_ACRONYMS.has(acr)) {
    return { w: SYMBOL_SIZE_SMALL, h: SYMBOL_SIZE_SMALL };
  }
  if (EQUIPMENT_TERMS.some((t) => name.includes(t))) {
    return { w: SYMBOL_SIZE_EQUIPMENT, h: SYMBOL_SIZE_EQUIPMENT };
  }
  if (cat === 'symbols_markers' || cat === 'symbol' || cat === 'legends') {
    return { w: SYMBOL_SIZE_SMALL, h: SYMBOL_SIZE_SMALL };
  }
  if (cat === 'logos' || cat === 'reference_pages') {
    return { w: SYMBOL_SIZE_LARGE, h: SYMBOL_SIZE_LARGE };
  }
  if (cat === 'panels_enclosures' || cat === 'equipment' || cat === 'hvac' || cat === 'refrigeration') {
    return { w: SYMBOL_SIZE_EQUIPMENT, h: SYMBOL_SIZE_EQUIPMENT };
  }
  if (cat) {
    return { w: SYMBOL_SIZE_EQUIPMENT, h: SYMBOL_SIZE_EQUIPMENT };
  }
  return { w: SYMBOL_SIZE_SMALL, h: SYMBOL_SIZE_SMALL };
}

export function scaleImageToSize(
  imgW: number,
  imgH: number,
  targetW: number,
  targetH: number,
): number {
  const iw = Math.max(1, imgW);
  const ih = Math.max(1, imgH);
  return Math.min(targetW / iw, targetH / ih);
}
