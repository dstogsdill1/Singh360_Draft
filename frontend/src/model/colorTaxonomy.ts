export const COLOR_TAXONOMY = {
  'control-admin': { label: 'Control / Admin', color: '#222831' },
  'page-manifest': { label: 'Page Manifest / Index', color: '#FFC000' },
  'included-front-matter': { label: 'Included Data / Front Matter', color: '#F59E0B' },
  'network-data': { label: 'Network / Data', color: '#2563EB' },
  lighting: { label: 'Lighting', color: '#EA580C' },
  'manual-hybrid': { label: 'Manual / Hybrid Layout', color: '#4F46E5' },
  'field-instructions': { label: 'Field Instructions', color: '#7C3AED' },
  'commissioning-closeout': { label: 'Commissioning / Closeout', color: '#16A34A' },
  'excluded-archived': { label: 'Excluded / Internal / Archived', color: '#9CA3AF' },
  'error-conflict': { label: 'Error / Conflict', color: '#DC2626' },
} as const;

export type ColorCategory = keyof typeof COLOR_TAXONOMY;

export function colorFor(category?: string, included = true): string {
  if (!included) return COLOR_TAXONOMY['excluded-archived'].color;
  return COLOR_TAXONOMY[(category || 'control-admin') as ColorCategory]?.color
    || COLOR_TAXONOMY['control-admin'].color;
}
