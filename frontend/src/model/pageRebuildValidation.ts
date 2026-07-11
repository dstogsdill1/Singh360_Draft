import type { PageBlock, PageModel } from './types';
import {
  blockAllowsContinuation,
  blockMinScale,
  excelBestScale,
  PAGE_BODY_BUDGET,
  PAGE_BODY_WIDTH,
} from './excelRange';

const CROP_RE = /scaled\/cropped|exceeds one page/i;

export interface RebuildValidationResult {
  ok: boolean;
  issues: string[];
}

function collectWarnings(page: PageModel, block: PageBlock | undefined): string[] {
  const out = [...(page.layoutWarnings ?? [])];
  if (block?.layoutWarnings?.length) out.push(...block.layoutWarnings);
  return out;
}

function hasMeaningfulContent(block: PageBlock | undefined): boolean {
  if (!block) return false;
  if (block.type === 'idfNetworkTable') {
    const rows = block.rows?.length ?? 0;
    const left = block.leftRows?.length ?? 0;
    const right = block.rightRows?.length ?? 0;
    return rows + left + right > 0;
  }
  if (block.type === 'excelRange') {
    const grid = block.grid ?? [];
    return grid.some((row) => row.some((c) => String(c ?? '').trim()));
  }
  if (block.type === 'table' || block.type === 'matrix') {
    return (block.rows?.length ?? 0) > 0;
  }
  return true;
}

function effectiveFontPt(block: PageBlock): number | null {
  if (block.type === 'idfNetworkTable' && block.fontSize != null) return block.fontSize;
  if (block.type === 'excelRange') {
    const scale = excelBestScale(block);
    return scale * 9;
  }
  if (block.bodyFontPx) return block.bodyFontPx * 0.75;
  return null;
}

function isTinyUpperLeft(block: PageBlock): boolean {
  if (block.type !== 'excelRange') return false;
  const scale = excelBestScale(block);
  const w = (block.colWidths ?? []).reduce((a, b) => a + b, 0);
  const h = (block.rowHeights ?? []).reduce((a, b) => a + b, 0);
  const scaledW = w * scale;
  const scaledH = h * scale;
  const rowCount = block.grid?.length ?? 0;
  return (
    rowCount > 3
    && scaledW < PAGE_BODY_WIDTH * 0.35
    && scaledH < PAGE_BODY_BUDGET * 0.35
  );
}

/** Validate a rebuilt page before replacing the live normalized page. */
export function validatePageRebuild(_before: PageModel, after: PageModel): RebuildValidationResult {
  const issues: string[] = [];
  const blocks = after.blocks ?? [];
  const block = blocks[0];

  if (!blocks.length || !block) {
    issues.push('Page is blank — no content blocks.');
    return { ok: false, issues };
  }

  if (!hasMeaningfulContent(block)) {
    issues.push('Page content is empty.');
  }

  for (const w of collectWarnings(after, block)) {
    if (CROP_RE.test(w)) issues.push(w);
  }

  if (block.type === 'excelRange') {
    const scale = excelBestScale(block);
    const minScale = blockMinScale(block);
    if (!blockAllowsContinuation(block) && scale < minScale) {
      issues.push('Range exceeds one page; scaled/cropped (continuation disabled).');
    }
    if (isTinyUpperLeft(block)) {
      issues.push('Table is pushed into a tiny upper-left block.');
    }
  }

  if (block.type === 'idfNetworkTable') {
    const cw = block.contentWidth ?? 0;
    const hasTwoUp = (block.leftRows?.length ?? 0) + (block.rightRows?.length ?? 0) > 0;
    if (hasTwoUp && cw < PAGE_BODY_WIDTH * 0.5) {
      issues.push('Network table is too narrow for the page body.');
    }
  }

  const fontPt = effectiveFontPt(block);
  if (fontPt != null && fontPt < 7) {
    issues.push(`Effective font is ${fontPt.toFixed(1)}pt (below 7pt readable floor).`);
  }

  return { ok: issues.length === 0, issues };
}
