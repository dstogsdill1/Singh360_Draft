import type { LibV2Component } from '../api/client';

export interface SymbolLegendRowDraft {
  id: string;
  enabled: boolean;
  label: string;
  acronym?: string;
  componentId?: string;
  symbolUrl?: string;
  searchTerms?: string[];
  preferredRep?: 'edge' | 'bw' | 'source';
  category?: string;
  defaultWidth?: number;
  defaultHeight?: number;
}

export interface SymbolLegendTemplate {
  id: string;
  name: string;
  category: string;
  title: string;
  rows: SymbolLegendRowDraft[];
}

export interface SymbolLegendInsertRow {
  label: string;
  symbolUrl?: string;
  name?: string;
  acronym?: string;
  iconSize?: number;
  category?: string;
  defaultWidth?: number;
  defaultHeight?: number;
}

export interface SymbolLegendInsertConfig {
  title: string;
  rows: SymbolLegendInsertRow[];
}

function row(
  id: string,
  label: string,
  searchTerms: string[],
  acronym?: string,
): SymbolLegendRowDraft {
  return { id, enabled: true, label, acronym, searchTerms, preferredRep: 'bw' };
}

export const BUILTIN_SYMBOL_LEGEND_TEMPLATES: SymbolLegendTemplate[] = [
  {
    id: 'refrigeration_wicp',
    name: 'Refrigeration Standard',
    category: 'refrigeration',
    title: 'SYMBOL LEGEND',
    rows: [
      row('li', 'LI — Leak Indicator Horn/Strobe', ['leak indicator', 'li leak'], 'LI'),
      row('da', 'DA — Door Open Horn/Strobe', ['door open', 'da door'], 'DA'),
      row('ls', 'LS — HFC Refrigerant Leak Sensor', ['hfc refrigerant leak', 'ls hfc'], 'LS'),
      row('lsc', 'LSc — CO2 Refrigerant Leak Sensor', ['co2 refrigerant leak', 'lsc'], 'LSc'),
      row('es', 'ES — Entrapment Horn/Strobe', ['entrapment horn', 'es entrapment'], 'ES'),
      row('ea', 'EA — Entrapment Alarm', ['entrapment alarm', 'ea entrapment'], 'EA'),
    ],
  },
  {
    id: 'signage',
    name: 'Signage Standard',
    category: 'signage',
    title: 'SYMBOL LEGEND',
    rows: [
      row('person_trapped', 'Person Trapped Inside', ['person trapped inside', 'person trapped'], ''),
      row('leak_dne', 'When Lit Leak Do Not Enter', ['leak do not enter', 'when lit'], ''),
      row('help_trapped', 'HELP TRAPPED', ['help trapped'], ''),
    ],
  },
  {
    id: 'interior_devices',
    name: 'Interior Device Standard',
    category: 'interior',
    title: 'SYMBOL LEGEND',
    rows: [
      row('rdm_dm', 'RDM Data Manager', ['rdm data manager', 'data manager']),
      row('rdm_idf', 'RDM IDF', ['rdm idf', 'idf network']),
      row('wicp', 'WICP', ['wicp']),
      row('lcp', 'LCP', ['lcp panel', 'lcp']),
      row('powerscout', 'Power Monitor', ['powerscout', 'power monitor', 'power scout']),
      row('orbit', 'Orbit TouchXL', ['orbit touch']),
      row('amber', 'Amber Strobe', ['amber alarm strobe', 'amber strobe']),
      row('red', 'Red Strobe', ['red alarm strobe', 'red strobe']),
      row('temp_probe', 'Temp Probe', ['temp probe', 'computer room temp', 'pharmacy temp']),
    ],
  },
  {
    id: 'exterior_devices',
    name: 'Exterior Device Location Symbols',
    category: 'exterior',
    title: 'SYMBOL LEGEND',
    rows: [
      row('pacu', 'PACU', ['pacu']),
      row('oau', 'OAU', ['oau outside air']),
      row('rack', 'Rack', ['refrigeration rack', 'co2 refrigeration rack']),
      row('rdm_idf', 'RDM IDF', ['rdm idf', 'idf']),
      row('lcp', 'LCP', ['lcp']),
      row('light_oat', 'Light Level / OAT Sensor', ['light level', 'oat sensor']),
      row('bacnet', 'BACnet Loop', ['bacnet']),
      row('cat6', 'CAT6', ['cat6']),
      row('roof', 'Roof Sensor', ['roof sensor']),
    ],
  },
  {
    id: 'lighting',
    name: 'Lighting Symbols',
    category: 'lighting',
    title: 'SYMBOL LEGEND',
    rows: [
      row('lcp', 'LCP', ['lcp']),
      row('contactor', 'Lighting Contactor', ['lighting contactor', 'contactor']),
      row('lt', 'Light Level Sensor', ['light level sensor', 'lt light']),
      row('oat', 'OAT Sensor', ['oat outside air temp', 'outside air temp']),
      row('dim', 'Dimming Zone', ['dimming zone']),
      row('router', 'BACnet Router', ['bacnet router']),
    ],
  },
  {
    id: 'power_metering',
    name: 'Power Metering Symbols',
    category: 'power',
    title: 'SYMBOL LEGEND',
    rows: [
      row('ps48', 'PowerScout PS48', ['powerscout ps48', 'ps48']),
      row('ct', 'Split-Core CT', ['split-core ct', 'split core ct']),
      row('rog', 'Rogowski Coil', ['rogowski']),
      row('mdp', 'MDP', ['mdp']),
      row('dp1', 'DP1', ['dp1']),
      row('panel', 'Panel', ['panel']),
    ],
  },
  {
    id: 'custom',
    name: 'Custom',
    category: 'custom',
    title: 'SYMBOL LEGEND',
    rows: [],
  },
];

function repUrl(c: LibV2Component, rep: 'edge' | 'bw' | 'source'): string {
  if (rep === 'bw' && c.bwUrl) return c.bwUrl;
  if (rep === 'edge' && c.edgeUrl) return c.edgeUrl;
  if (c.bwUrl) return c.bwUrl;
  if (c.edgeUrl) return c.edgeUrl;
  return c.thumbnailUrl || c.sourceUrl || '';
}

export function matchComponent(
  components: LibV2Component[],
  terms: string[],
  preferredRep: 'edge' | 'bw' | 'source' = 'bw',
): LibV2Component | undefined {
  const needles = terms.map((t) => t.toLowerCase().trim()).filter(Boolean);
  if (!needles.length) return undefined;
  let best: { score: number; comp: LibV2Component } | undefined;
  for (const c of components) {
    const hay = [
      c.displayName,
      c.defaultLabel,
      c.partNumber,
      c.id,
      ...(c.aliases || []),
    ]
      .join(' ')
      .toLowerCase();
    let score = 0;
    for (const n of needles) {
      if (hay.includes(n)) score += n.length;
    }
    if (!score) continue;
    if (repUrl(c, preferredRep)) score += 5;
    if (!best || score > best.score) best = { score, comp: c };
  }
  return best?.comp;
}

export function hydrateTemplateRows(
  template: SymbolLegendTemplate,
  components: LibV2Component[],
): SymbolLegendRowDraft[] {
  return template.rows.map((r) => {
    const comp = r.searchTerms?.length
      ? matchComponent(components, r.searchTerms, r.preferredRep || 'bw')
      : undefined;
    const url = comp ? repUrl(comp, r.preferredRep || 'bw') : r.symbolUrl;
    return {
      ...r,
      componentId: comp?.id || r.componentId,
      symbolUrl: url || r.symbolUrl,
      category: comp?.category || r.category,
      defaultWidth: comp?.defaultWidth ?? r.defaultWidth,
      defaultHeight: comp?.defaultHeight ?? r.defaultHeight,
      label: r.label,
    };
  });
}

export function rowsFromTemplatePayload(
  payload: { title?: string; rows?: Array<Record<string, unknown>> },
  components: LibV2Component[],
): { title: string; rows: SymbolLegendRowDraft[] } {
  const title = String(payload.title || 'SYMBOL LEGEND');
  const rows: SymbolLegendRowDraft[] = (payload.rows || []).map((raw, i) => {
    const searchTerms = Array.isArray(raw.searchTerms)
      ? raw.searchTerms.map(String)
      : raw.componentId
        ? []
        : [];
    const draft: SymbolLegendRowDraft = {
      id: String(raw.id || `row_${i}`),
      enabled: raw.enabled !== false,
      label: String(raw.label || ''),
      acronym: raw.acronym ? String(raw.acronym) : undefined,
      componentId: raw.componentId ? String(raw.componentId) : undefined,
      symbolUrl: raw.symbolUrl ? String(raw.symbolUrl) : undefined,
      searchTerms,
      preferredRep: (raw.preferredRep as 'edge' | 'bw' | 'source') || 'bw',
      category: raw.category ? String(raw.category) : undefined,
      defaultWidth: raw.defaultWidth != null ? Number(raw.defaultWidth) : undefined,
      defaultHeight: raw.defaultHeight != null ? Number(raw.defaultHeight) : undefined,
    };
    if (!draft.symbolUrl && draft.componentId) {
      const comp = components.find((c) => c.id === draft.componentId);
      if (comp) {
        draft.symbolUrl = repUrl(comp, draft.preferredRep || 'bw');
        draft.category = comp.category;
        draft.defaultWidth = comp.defaultWidth;
        draft.defaultHeight = comp.defaultHeight;
      }
    }
    if (!draft.symbolUrl && searchTerms.length) {
      const comp = matchComponent(components, searchTerms, draft.preferredRep || 'bw');
      if (comp) {
        draft.componentId = comp.id;
        draft.symbolUrl = repUrl(comp, draft.preferredRep || 'bw');
        draft.category = comp.category;
        draft.defaultWidth = comp.defaultWidth;
        draft.defaultHeight = comp.defaultHeight;
      }
    }
    return draft;
  });
  return { title, rows };
}
