const LEGACY_LSC_COMPONENT_ID = 'symbols_markers_s360_7a7d4d97334a';
const LSC_NAME = 'LSc — CO2 Refrigerant Leak Detector — CT1O-A3D — Senva';

export interface LeakSensorCanvasMigration {
  objects: Record<string, unknown>[];
  repaired: number;
}

/**
 * Upgrade only saved objects tied to the audited LS2 stable component ID.
 * Asset URLs intentionally remain unchanged: their contents are migrated in
 * place so old saves, copy/paste payloads, and exports keep resolving safely.
 */
export function normalizeLeakSensorCanvasObjects(
  objects: Record<string, unknown>[],
): LeakSensorCanvasMigration {
  let repaired = 0;

  const visit = (
    raw: Record<string, unknown>,
    inheritedLegacy = false,
    inheritedLegend = false,
  ): Record<string, unknown> => {
    const record = { ...raw };
    const source = String(record.sourceUrl || record.src || '');
    const oldAcronym = String(record.symAcronym || '').replace('₂', '2').toUpperCase() === 'LS2';
    const legacyAsset = source.includes('singh360__ls2__co2-refrigerant-leak-sensor.svg');
    const legend = inheritedLegend || record.objName === 'Singh360 Symbol Legend';
    const legacy = inheritedLegacy || record.libraryComponentId === LEGACY_LSC_COMPONENT_ID;
    const legacyNode = legacy || legacyAsset || (legend && oldAcronym);
    if (legacyNode) {
      const before = JSON.stringify([
        record.objName,
        record.symAcronym,
        record.placedSymbolConfig,
      ]);
      if (typeof record.objName === 'string' && /LS(?:2|₂)|CO2 REFRIGERANT LEAK SENSOR/i.test(record.objName)) {
        record.objName = record.objName
          .replace(/LS(?:2|₂)/gi, 'LSc')
          .replace(/CO2 REFRIGERANT LEAK SENSOR/gi, 'CO2 Refrigerant Leak Detector');
      }
      if (legacy || legacyAsset || oldAcronym) record.symAcronym = 'LSc';
      if (record.placedSymbolConfig && typeof record.placedSymbolConfig === 'object') {
        record.placedSymbolConfig = {
          ...(record.placedSymbolConfig as Record<string, unknown>),
          name: LSC_NAME,
        };
      }
      if (before !== JSON.stringify([record.objName, record.symAcronym, record.placedSymbolConfig])) repaired += 1;
    }
    if (legend && typeof record.text === 'string') {
      if (/^CO2 REFRIGERANT LEAK SENSOR$/i.test(record.text.trim())) {
        record.text = 'CO2 Refrigerant Leak Detector';
        repaired += 1;
      } else if (/^REFRIGERANT LEAK DETECTION SENSOR$/i.test(record.text.trim())) {
        record.text = 'Leak Sensor for HFCs';
        repaired += 1;
      }
    }
    if (Array.isArray(record.objects)) {
      record.objects = (record.objects as unknown[]).map((child) =>
        child && typeof child === 'object' ? visit(child as Record<string, unknown>, legacy, legend) : child,
      );
    }
    return record;
  };

  return { objects: objects.map((object) => visit(object)), repaired };
}
