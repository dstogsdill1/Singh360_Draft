export function newCanvasObjectId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
  return `canvas_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

export function assignFreshCanvasObjectIds<T extends Record<string, unknown>>(source: T): T {
  const copy: Record<string, unknown> = { ...source, objectId: newCanvasObjectId() };
  if (Array.isArray(source.objects)) {
    copy['objects'] = source.objects.map((child) =>
      child && typeof child === 'object'
        ? assignFreshCanvasObjectIds(child as Record<string, unknown>)
        : child,
    );
  }
  return copy as T;
}
