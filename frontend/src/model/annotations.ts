import { assignFreshCanvasObjectIds } from './canvasObjectIdentity';
import type {
  AnnotationSettings,
  AnnotationStyle,
} from './types';

export const DEFAULT_ANNOTATION_SETTINGS: AnnotationSettings = {
  visible: true,
  locked: false,
  includeInExport: true,
};

export const DEFAULT_ANNOTATION_STYLE: AnnotationStyle = {
  color: '#d71920',
  opacity: 1,
  strokeWidth: 3,
  fillColor: '#d71920',
  fillOpacity: 0,
  fontSize: 18,
  bold: false,
  backgroundColor: '#ffffff',
  backgroundOpacity: 0,
  highlightColor: '#ffe600',
  highlightOpacity: 0.3,
  highlightWidth: 24,
  penWidth: 4,
  smoothing: 2,
};

export function normalizeAnnotationSettings(
  value: Partial<AnnotationSettings> | null | undefined,
): AnnotationSettings {
  return {
    visible: value?.visible ?? DEFAULT_ANNOTATION_SETTINGS.visible,
    locked: value?.locked ?? DEFAULT_ANNOTATION_SETTINGS.locked,
    includeInExport: value?.includeInExport ?? DEFAULT_ANNOTATION_SETTINGS.includeInExport,
  };
}

export function freshAnnotationObjects(
  objects: Record<string, unknown>[] | null | undefined,
): Record<string, unknown>[] {
  return (objects ?? []).map((object) => assignFreshCanvasObjectIds(object));
}
