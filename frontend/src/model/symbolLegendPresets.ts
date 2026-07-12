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
    name: 'RDM WICP / Safety Standard',
    category: 'refrigeration',
    title: 'SYMBOL LEGEND',
    rows: [
      row('li', 'LI — Leak Indicator Horn/Strobe', ['LI Leak Indicator Horn/Strobe', 'refrigerant leak horn strobe'], 'LI'),
      row('da', 'DA — Door Open Horn/Strobe', ['DA Door Open Horn/Strobe', 'door open horn strobe'], 'DA'),
      row('ls', 'LS — HFC Refrigerant Leak Sensor', ['LS HFC Refrigerant Leak Sensor', 'HFC leak sensor'], 'LS'),
      row('lsb', 'LSB — HFC Leak Sensor, Metal Enclosure', ['LSB HFC Leak Sensor', 'LS-B', 'metal enclosure'], 'LSB'),
      row('lsg', 'LSG — CTI HFC Refrigerant Leak Sensor', ['LSG CTI HFC', 'LS-G', 'CTI HFC'], 'LSG'),
      row('lsc', 'LSC — CO2 Refrigerant Leak Sensor', ['LSC CO2 Refrigerant Leak Sensor', 'LSc', 'LS CO2'], 'LSC'),
      row('es', 'ES — Entrapment Switch', ['ES Entrapment Switch', 'entrapment switch'], 'ES'),
      row('ea', 'EA — Entrapment Horn/Strobe', ['EA Entrapment Horn/Strobe', 'entrapment horn strobe'], 'EA'),
      row('hs', 'HS — Leak / Horn Silencer Button', ['HS Leak Horn Silencer', 'horn silencer', 'leak silencer'], 'HS'),
    ],
  },
  {
    id: 'signage',
    name: 'RDM Safety Signage Standard',
    category: 'signage',
    title: 'SIGNAGE LEGEND',
    rows: [
      row('person_trapped', 'EA-PTI — Person Trapped Inside', ['Person Trapped Inside Sign Symbol', 'EA-PTI'], 'EA-PTI'),
      row('leak_dne', 'LI-A — When Lit: Refrigerant Leak / Do Not Enter', ['When Lit Refrigerant Leak Do Not Enter Sign Symbol', 'LI-A'], 'LI-A'),
      row('help_trapped', 'EA-MTS — HELP TRAPPED / PERSONA ATRAPADA', ['HELP TRAPPED PERSONA ATRAPADA Sign Symbol', 'EA-MTS'], 'EA-MTS'),
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
    id: 'refrigeration_plan',
    name: 'RDM Refrigeration Plan Standard',
    category: 'refrigeration',
    title: 'REFRIGERATION PLAN LEGEND',
    rows: [
      row('ts', 'TS — Temperature Sensor', ['TS Temperature Sensor', 'Temp Sensor'], 'TS'),
      row('ds', 'DS — Defrost Sensor', ['DS Defrost Sensor', 'Defrost Termination'], 'DS'),
      row('dts', 'DTS — Dual Temperature Switch', ['DTS Dual Temperature Switch', 'Dual Temp Switch'], 'DTS'),
      row('eepr_e', 'Electronic EEPR', ['Electronic EEPR Plan Marker'], 'E-EEPR'),
      row('eepr_m', 'Mechanical EEPR', ['Mechanical EEPR Plan Marker'], 'M-EEPR'),
      row('defrost', 'Electric Defrost', ['Electric Defrost Plan Marker'], 'DEF'),
      row('lls_plan', 'Liquid Line Solenoid', ['Liquid Line Solenoid Plan Marker'], 'LLS'),
    ],
  },
  {
    id: 'refrigeration_line',
    name: 'RDM Refrigeration Line Standard',
    category: 'refrigeration',
    title: 'REFRIGERATION SYMBOL LEGEND',
    rows: [
      row('lls_open', 'LLS — Liquid Line Solenoid Open', ['Liquid Line Solenoid Open'], 'LLS'),
      row('lls_closed', 'LLS — Liquid Line Solenoid Closed', ['Liquid Line Solenoid Closed'], 'LLS'),
      row('eev', 'EEV — Electronic Expansion Valve', ['Electronic Expansion Valve'], 'EEV'),
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
