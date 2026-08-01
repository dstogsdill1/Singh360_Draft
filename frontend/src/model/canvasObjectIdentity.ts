export function newCanvasObjectId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
  return `canvas_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

const INTERNAL_OBJECT_ID_REFERENCE_KEYS = new Set([
  'smartParentId',
]);

function visitCanvasObjectTree(
  value: unknown,
  visit: (record: Record<string, unknown>) => void,
): void {
  if (Array.isArray(value)) {
    value.forEach((item) => visitCanvasObjectTree(item, visit));
    return;
  }
  if (!value || typeof value !== 'object') return;

  const record = value as Record<string, unknown>;
  visit(record);
  if (Array.isArray(record.objects)) {
    record.objects.forEach((child) => visitCanvasObjectTree(child, visit));
  }
}

/**
 * Deep-clone one serialized Fabric object tree and give every group/child its
 * own identity. Stable content identities (for example libraryComponentId,
 * componentId, and assemblyId) are deliberately left unchanged. References
 * between objects inside the cloned tree are remapped to the corresponding
 * fresh objectId.
 */
export function assignFreshCanvasObjectIds<T extends Record<string, unknown>>(source: T): T {
  const copy = structuredClone(source) as T;
  const replacements = new Map<string, string>();

  visitCanvasObjectTree(copy, (record) => {
    const previous = typeof record.objectId === 'string' ? record.objectId : '';
    const fresh = newCanvasObjectId();
    record.objectId = fresh;
    if (previous) replacements.set(previous, fresh);
  });

  visitCanvasObjectTree(copy, (record) => {
    for (const key of INTERNAL_OBJECT_ID_REFERENCE_KEYS) {
      const previous = record[key];
      if (typeof previous === 'string' && replacements.has(previous)) {
        record[key] = replacements.get(previous) as string;
      }
    }
  });

  return copy;
}
