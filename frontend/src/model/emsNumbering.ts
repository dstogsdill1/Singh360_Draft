import type { PageModel } from './types';

/**
 * Singh360 EMS drawing-package numbering standard.
 *
 * Front matter uses a 0-series (EMS 0.0 … EMS 0.7). Technical content uses
 * numbered families EMS 1.x … EMS 9.x. Sheet codes are separate from the
 * auto "Page X of Y" package order.
 */

export type PageFamily =
  | { kind: 'front'; minor: number; label: string }
  | { kind: 'family'; series: number; label: string }
  | { kind: 'unknown'; label: string };

// Fixed front-matter sub-index by canonical category (order matters — first match wins).
const FRONT_MATTER: Array<{ minor: number; label: string; keys: string[] }> = [
  { minor: 0, label: 'Cover / Project Info', keys: ['cover', 'project info', 'title sheet'] },
  { minor: 1, label: 'Sheet Index / TOC', keys: ['sheet index', 'index', 'table of contents', 'toc', 'contents'] },
  { minor: 2, label: 'Project Directory / Contacts', keys: ['directory', 'contacts', 'project team'] },
  { minor: 3, label: 'General Notes / Guidelines', keys: ['guideline', 'general note', 'standards', 'legend key'] },
  { minor: 4, label: 'Project Scope / Workflow', keys: ['scope', 'workflow', 'sequence of work'] },
  { minor: 5, label: 'Responsibility Matrix', keys: ['responsibilit', 'raci', 'matrix of responsibilit'] },
  { minor: 6, label: 'Bill of Materials / Equipment Summary', keys: ['bill of material', 'bom', 'equipment summary', 'equipment list', 'material list'] },
  { minor: 7, label: 'Revision Log / Intake', keys: ['revision log', 'intake', 'issue history', 'revision history'] },
];

// Technical families (series 1–9). Ordered by classification precedence
// (most specific first); the numbering loop still assigns codes by series number,
// so a "schematic" sheet lands in family 8 even if it also mentions lighting.
const FAMILIES: Array<{ series: number; label: string; keys: string[] }> = [
  { series: 8, label: 'Wiring / Panel Schematics', keys: ['wiring schematic', 'panel schematic', 'lcp schematic', 'schematic', 'panel detail', 'wiring diagram', 'one-line', 'one line'] },
  { series: 3, label: 'Refrigeration / Rack / DLE', keys: ['dle', 'wicp', 'case control', 'refrigerat', 'leak detection', 'leak sensor', 'suction', 'condenser', 'evaporator', 'ccg'] },
  { series: 2, label: 'Network / Data', keys: ['idf', 'mdf', 'data manager', 'bacnet', 'network', 'ip schedule', 'rack a', 'rack b', 'rack schedule', 'patch panel', 'switch'] },
  { series: 5, label: 'Lighting', keys: ['lcp', 'lighting', 'tdb', 'output matrix', 'dimming', 'photocell', 'light level'] },
  { series: 4, label: 'Mechanical / HVAC', keys: ['pacu', 'hvac', 'mechanical', 'rtu', 'ahu', 'make-up air'] },
  { series: 6, label: 'Power / Metering', keys: ['power monitor', 'metering', 'electrical panel', 'pmp', 'wattnode', 'powerscout', 'ct '] },
  { series: 1, label: 'Field Instructions', keys: ['field instruction', 'gc field', 'ec field', 'dc field', 'contractor execution', 'ems remote', 'instructions'] },
  { series: 7, label: 'Device Location / Floor Plans', keys: ['interior location', 'exterior location', 'device location', 'floor plan', 'overall layout', 'location plan', 'layout'] },
  { series: 9, label: 'Reference / Notes / As-Built', keys: ['as-built', 'as built', 'appendix', 'reference', 'company info', 'singh360'] },
];

function haystack(p: PageModel): string {
  return `${p.sheetTitle ?? ''} ${p.sheetTab ?? ''} ${(p as { template?: string }).template ?? ''}`.toLowerCase();
}

export function classifyPageFamily(p: PageModel): PageFamily {
  const hay = haystack(p);
  for (const fm of FRONT_MATTER) {
    if (fm.keys.some((k) => hay.includes(k))) return { kind: 'front', minor: fm.minor, label: fm.label };
  }
  for (const fam of FAMILIES) {
    if (fam.keys.some((k) => hay.includes(k))) return { kind: 'family', series: fam.series, label: fam.label };
  }
  return { kind: 'unknown', label: 'Unclassified' };
}

const CONT_SUFFIX = ['', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

/**
 * Generate EMS front-matter + family codes for the included pages.
 * Returns a Map of page.id -> "EMS x.y" (and continuation suffixes).
 */
export function generateEmsCodes(pages: PageModel[], prefix = 'EMS'): Map<string, string> {
  const map = new Map<string, string>();
  const included = pages.filter((p) => p.include);
  const bases = included.filter((p) => !p.continuationOf);

  // 1) Assign front-matter sheets to their fixed 0.x sub-index (bump on collision).
  const usedFrontMinors = new Set<number>();
  const baseCodeById = new Map<string, string>();
  const frontBases: PageModel[] = [];
  const familyBuckets = new Map<number, PageModel[]>();
  const unknownBases: PageModel[] = [];

  for (const b of bases) {
    const fam = classifyPageFamily(b);
    if (fam.kind === 'front') frontBases.push(b);
    else if (fam.kind === 'family') {
      const arr = familyBuckets.get(fam.series) ?? [];
      arr.push(b);
      familyBuckets.set(fam.series, arr);
    } else unknownBases.push(b);
  }

  for (const b of frontBases) {
    const fam = classifyPageFamily(b) as { kind: 'front'; minor: number };
    let minor = fam.minor;
    while (usedFrontMinors.has(minor)) minor += 1;
    usedFrontMinors.add(minor);
    const code = `${prefix} 0.${minor}`;
    baseCodeById.set(b.id, code);
    map.set(b.id, code);
  }

  // 2) Technical families, numbered X.1, X.2… within each family by page order.
  for (let series = 1; series <= 9; series += 1) {
    const arr = familyBuckets.get(series) ?? [];
    arr.forEach((b, i) => {
      const code = `${prefix} ${series}.${i + 1}`;
      baseCodeById.set(b.id, code);
      map.set(b.id, code);
    });
  }

  // 3) Unknown pages get a 9.x reference family tail so nothing is left blank.
  const refArr = familyBuckets.get(9) ?? [];
  let refN = refArr.length;
  for (const b of unknownBases) {
    refN += 1;
    const code = `${prefix} 9.${refN}`;
    baseCodeById.set(b.id, code);
    map.set(b.id, code);
  }

  // 4) Continuations inherit the base code + a letter suffix.
  for (const p of included) {
    if (!p.continuationOf) continue;
    const baseCode = baseCodeById.get(p.continuationOf) ?? p.sheetCode;
    const idx = Math.min(Math.max(p.continuationIndex ?? 1, 1), CONT_SUFFIX.length - 1);
    map.set(p.id, `${baseCode}${CONT_SUFFIX[idx]}`);
  }

  return map;
}
