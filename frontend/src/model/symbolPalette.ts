import type { CSSProperties } from 'react';

export type SymbolPalettePattern =
  | 'solid'
  | 'outline'
  | 'double-outline'
  | 'split-vertical'
  | 'split-horizontal'
  | 'diagonal'
  | 'crosshatch';

export interface SymbolPaletteChoice {
  id: string;
  label: string;
  color: string;
  color2: string;
  pattern: SymbolPalettePattern;
}

export const SYMBOL_PALETTE: SymbolPaletteChoice[] = [
  { id: 'red', label: 'Red', color: '#e53935', color2: '#e53935', pattern: 'solid' },
  { id: 'green', label: 'Green', color: '#00a651', color2: '#00a651', pattern: 'solid' },
  { id: 'yellow', label: 'Yellow', color: '#ffd400', color2: '#ffd400', pattern: 'solid' },
  { id: 'blue', label: 'Blue', color: '#1e73be', color2: '#1e73be', pattern: 'solid' },
  { id: 'orange', label: 'Orange', color: '#ff7a00', color2: '#ff7a00', pattern: 'solid' },
  { id: 'purple', label: 'Purple', color: '#8e44ad', color2: '#8e44ad', pattern: 'solid' },
  { id: 'cyan', label: 'Cyan', color: '#00a8cc', color2: '#00a8cc', pattern: 'solid' },
  { id: 'pink', label: 'Pink', color: '#e84393', color2: '#e84393', pattern: 'solid' },
  { id: 'red-green', label: 'Red / Green', color: '#e53935', color2: '#00a651', pattern: 'split-vertical' },
  { id: 'red-blue', label: 'Red / Blue', color: '#e53935', color2: '#1e73be', pattern: 'split-vertical' },
  { id: 'yellow-blue', label: 'Yellow / Blue', color: '#ffd400', color2: '#1e73be', pattern: 'split-vertical' },
  { id: 'yellow-green', label: 'Yellow / Green', color: '#ffd400', color2: '#00a651', pattern: 'split-vertical' },
  { id: 'orange-blue', label: 'Orange / Blue', color: '#ff7a00', color2: '#1e73be', pattern: 'split-vertical' },
  { id: 'purple-green', label: 'Purple / Green', color: '#8e44ad', color2: '#00a651', pattern: 'split-vertical' },
  { id: 'red-yellow', label: 'Red / Yellow', color: '#e53935', color2: '#ffd400', pattern: 'split-vertical' },
  { id: 'blue-green', label: 'Blue / Green', color: '#1e73be', color2: '#00a651', pattern: 'split-vertical' },
];

export function rgbaHex(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return `rgba(255, 212, 0, ${alpha})`;
  const value = Number.parseInt(clean, 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

export function symbolMarkerStyle(
  choice: Pick<SymbolPaletteChoice, 'color' | 'color2' | 'pattern'>,
  fillAlpha = 1,
  borderWidth = 2,
): CSSProperties {
  if (choice.pattern === 'split-vertical') {
    const fill = `linear-gradient(90deg, ${rgbaHex(choice.color, fillAlpha)} 0 50%, ${rgbaHex(choice.color2, fillAlpha)} 50% 100%)`;
    const outline = `linear-gradient(90deg, ${choice.color} 0 50%, ${choice.color2} 50% 100%)`;
    return {
      border: `${borderWidth}px solid transparent`,
      background: `${fill} padding-box, ${outline} border-box`,
      backgroundOrigin: 'border-box',
      backgroundClip: 'padding-box, border-box',
      boxSizing: 'border-box',
    };
  }
  return {
    border: `${borderWidth}px solid ${choice.color}`,
    background: rgbaHex(choice.color, fillAlpha),
    boxSizing: 'border-box',
  };
}

export function normalizeSymbolTemplateText(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
}

export function symbolTemplateKey(code: string, label: string): string {
  return `${normalizeSymbolTemplateText(code)}|${normalizeSymbolTemplateText(label)}`;
}

export function paletteChoiceById(id: string | undefined, index = 0): SymbolPaletteChoice {
  return SYMBOL_PALETTE.find((choice) => choice.id === id)
    ?? SYMBOL_PALETTE[index % SYMBOL_PALETTE.length];
}
