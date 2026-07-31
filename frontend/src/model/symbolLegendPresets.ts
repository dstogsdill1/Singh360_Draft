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
      row('li', 'LI - Leak Indicator Horn/Strobe', ['LI Leak Indicator Horn/Strobe', 'refrigerant leak horn strobe'], 'LI'),
      row('da', 'DA - Door Open Horn/Strobe', ['DA Door Open Horn/Strobe', 'door open horn strobe'], 'DA'),
      row('lsc', 'LSc — CO2 Refrigerant Leak Detector', ['LSc', 'LS2', 'LS₂', 'CO2 leak sensor', 'CT1O-A3D', 'Senva'], 'LSc'),
      row('lsg', 'LSg — Produce Prep Area HFC Sensor (Refrigerant Specific)', ['LSg', 'GG-R513A', 'CTI'], 'LSg'),
      row('ls', 'LS — Leak Sensor for HFCs', ['LS', 'REF-LK-832', 'EMC'], 'LS'),
      row('lsb', 'LSb — Leak Sensor for HFCs, w/metal enclosure (produce/market coolers)', ['LSb', 'REF-LK-832-MTL', 'EMC'], 'LSb'),
      row('es', 'ES - Entrapment Switch', ['ES Entrapment Switch', 'entrapment switch'], 'ES'),
      row('ea', 'EA - Entrapment Horn/Strobe', ['EA Entrapment Horn/Strobe', 'entrapment horn strobe'], 'EA'),
      row('hs', 'HS - Horn Silencer Button', ['HS Horn Silencer Button', 'horn silencer', 'leak silencer'], 'HS'),
    ],
  },
  {
    id: 'signage',
    name: 'RDM Safety Signage Standard',
    category: 'signage',
    title: 'SIGNAGE LEGEND',
    rows: [
      row('person_trapped', 'EA-PTI - Person Trapped Inside', ['Person Trapped Inside Sign Symbol', 'EA-PTI'], 'EA-PTI'),
      row('leak_dne', 'LI-A - When Lit: Refrigerant Leak / Do Not Enter', ['When Lit Refrigerant Leak Do Not Enter Sign', 'LI-A'], 'LI-A'),
      row('help_trapped', 'EA-MTS - HELP TRAPPED / PERSONA ATRAPADA', ['HELP TRAPPED PERSONA ATRAPADA Sign', 'EA-MTS'], 'EA-MTS'),
    ],
  },
  {
    id: 'interior_devices',
    name: 'Interior Device Standard',
    category: 'interior',
    title: 'SYMBOL LEGEND',
    rows: [
      row('rdm_dm', 'RDM Data Manager', ['RDM Data Manager', 'Data Manager']),
      row('rdm_idf', 'RDM IDF', ['RDM IDF Marker', 'RDM IDF']),
      row('mdf', 'MDF Server Rack', ['MDF Server Rack Marker', 'MDF']),
      row('wicp', 'WICP', ['WICP']),
      row('lcp', 'LCP', ['LCP']),
      row('powerscout', 'Power Monitor', ['PowerScout', 'Power Monitor']),
      row('orbit', 'Orbit TouchXL', ['Orbit TouchXL', 'Orbit Touch']),
      row('amber', 'Amber Alarm Strobe', ['Amber Alarm Strobe', 'High Temp Strobe']),
      row('red', 'Red Alarm Strobe', ['Red Alarm Strobe', 'Rack Alarm Strobe']),
      row('temp_probe', 'Temperature Probe', ['Temperature Probe', 'Temp Probe']),
    ],
  },
  {
    id: 'exterior_devices',
    name: 'Exterior Device Location Symbols',
    category: 'exterior',
    title: 'SYMBOL LEGEND',
    rows: [
      row('pacu', 'PACU', ['PACU']),
      row('oau', 'OAU', ['OAU', 'Outside Air Unit']),
      row('rack', 'Refrigeration Rack', ['Refrigeration Rack']),
      row('rdm_idf', 'RDM IDF', ['RDM IDF Marker', 'RDM IDF']),
      row('mdf', 'MDF Server Rack', ['MDF Server Rack Marker', 'MDF']),
      row('lcp', 'LCP', ['LCP']),
      row('light_oat', 'Light Level / OAT Sensor', ['Light Level', 'OAT Sensor']),
      row('router', 'BACnet Router', ['BACnet Router', 'BASRT-B']),
      row('roof', 'Roof Sensor', ['Roof Sensor']),
    ],
  },
  {
    id: 'lighting',
    name: 'Lighting Symbols',
    category: 'lighting',
    title: 'SYMBOL LEGEND',
    rows: [
      row('lcp', 'LCP', ['LCP']),
      row('contactor', 'Lighting Contactor', ['Lighting Contactor']),
      row('lt', 'Light Level Sensor', ['Light Level Sensor', 'LT']),
      row('oat', 'OAT Sensor', ['OAT Sensor', 'Outside Air Temperature']),
      row('dim', 'Dimming Zone', ['Dimming Zone']),
      row('router', 'BACnet Router', ['BACnet Router', 'BASRT-B']),
    ],
  },
  {
    id: 'power_metering',
    name: 'Power Metering Symbols',
    category: 'power',
    title: 'SYMBOL LEGEND',
    rows: [
      row('ps48', 'PowerScout PS48', ['PowerScout PS48', 'PS48']),
      row('ct', 'Split-Core CT', ['Split-Core CT', 'Split Core CT']),
      row('rog', 'Rogowski Coil', ['Rogowski']),
      row('mdp', 'MDP', ['MDP']),
      row('panel', 'Electrical Panel', ['Electrical Panel', 'Panel']),
    ],
  },
  {
    id: 'refrigeration_plan',
    name: 'RDM Refrigeration Plan Standard',
    category: 'refrigeration',
    title: 'REFRIGERATION PLAN LEGEND',
    rows: [
      row('ts', 'TS - Temperature Sensor', ['TS Temperature Sensor', 'Temp Sensor'], 'TS'),
      row('ds', 'DS - Defrost Sensor', ['DS Defrost Sensor', 'Defrost Termination'], 'DS'),
      row('dts', 'DTS - Dual Temperature Switch', ['DTS Dual Temperature Switch', 'Dual Temp Switch'], 'DTS'),
      row('eepr', 'EEPR - Electronic Evaporator Pressure Regulator', ['EEPR Electronic Evaporator Pressure Regulator', 'Electronic EEPR'], 'EEPR'),
      row('epr', 'EPR - Mechanical Evaporator Pressure Regulator', ['EPR Mechanical Evaporator Pressure Regulator', 'Mechanical EPR'], 'EPR'),
      row('defrost', 'DEF - Electric Defrost', ['Electric Defrost Marker'], 'DEF'),
      row('lls_plan', 'LLS - Liquid Line Solenoid', ['Liquid Line Solenoid Marker'], 'LLS'),
      row('anti_sweat', 'AS/TRIM - Anti-Sweat / Trim Heater', ['Anti-Sweat / Trim Heater'], 'AS/TRIM'),
      row('evap_fan', 'Evaporator Fan', ['Evaporator Fan']),
      row('cond_fan', 'Condenser Fan', ['Condenser Fan']),
      row('evaporator', 'Evaporator Coil', ['Evaporator Coil']),
      row('compressor', 'Compressor', ['Compressor']),
    ],
  },
  {
    id: 'refrigeration_line',
    name: 'RDM Refrigeration Line Standard',
    category: 'refrigeration',
    title: 'REFRIGERATION SYMBOL LEGEND',
    rows: [
      row('lls_open', 'LLS - Liquid Line Solenoid Open', ['Liquid Line Solenoid - Open'], 'LLS'),
      row('lls_closed', 'LLS - Liquid Line Solenoid Closed', ['Liquid Line Solenoid - Closed'], 'LLS'),
      row('eev', 'EEV - Electronic Expansion Valve', ['EEV Electronic Expansion Valve'], 'EEV'),
    ],
  },
  {
    id: 'wicp_hardware',
    name: 'RDM WICP Hardware Standard',
    category: 'wicp_hardware',
    title: 'WICP HARDWARE LEGEND',
    rows: [
      row('li_blue', 'Blue - Refrigerant Leak Horn/Strobe', ['Blue Refrigerant Leak Horn/Strobe']),
      row('da_yellow', 'Yellow - Door Open Horn/Strobe', ['Yellow Door Open Horn/Strobe']),
      row('ea_red', 'Red - Entrapment Horn/Strobe', ['Red Entrapment Horn/Strobe']),
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
