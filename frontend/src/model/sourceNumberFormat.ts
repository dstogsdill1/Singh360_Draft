export type SourceNumberAction =
  | 'general'
  | 'zero-decimals'
  | 'decrease-decimal'
  | 'increase-decimal'
  | 'comma'
  | 'currency'
  | 'percent'
  | 'multiply-10'
  | 'divide-10'
  | 'trim';

export interface SourceGridCell {
  r: number;
  c: number;
}

interface ParsedNumber {
  value: number;
  decimals: number;
  percent: boolean;
}

const MAX_DECIMALS = 8;
const NUMBER_RE = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

function decimalPlaces(text: string): number {
  const mantissa = text.toLowerCase().split('e', 1)[0];
  const dot = mantissa.indexOf('.');
  return dot < 0 ? 0 : Math.min(MAX_DECIMALS, mantissa.length - dot - 1);
}

function parseNumber(text: string): ParsedNumber | null {
  let raw = String(text ?? '').trim();
  if (!raw) return null;

  let negative = false;
  if (raw.startsWith('(') && raw.endsWith(')')) {
    negative = true;
    raw = raw.slice(1, -1).trim();
  }

  const percent = raw.endsWith('%');
  if (percent) raw = raw.slice(0, -1).trim();

  raw = raw.replace(/[$,\s]/g, '');
  if (!NUMBER_RE.test(raw)) return null;

  let value = Number(raw);
  if (!Number.isFinite(value)) return null;
  if (negative) value = -Math.abs(value);
  if (percent) value /= 100;

  return {
    value,
    decimals: decimalPlaces(raw),
    percent,
  };
}

function plainNumber(value: number): string {
  if (!Number.isFinite(value)) return '';
  if (Object.is(value, -0)) value = 0;
  if (Number.isInteger(value)) return String(value);
  return value
    .toFixed(12)
    .replace(/0+$/, '')
    .replace(/\.$/, '');
}

function fixed(value: number, decimals: number): string {
  const count = Math.max(0, Math.min(MAX_DECIMALS, decimals));
  return value.toFixed(count);
}

function withCommas(value: number, decimals: number): string {
  const count = Math.max(0, Math.min(MAX_DECIMALS, decimals));
  return value.toLocaleString('en-US', {
    minimumFractionDigits: count,
    maximumFractionDigits: count,
    useGrouping: true,
  });
}

export function formatSourceValue(text: string, action: SourceNumberAction): string {
  if (action === 'trim') {
    return String(text ?? '').replace(/\s+/g, ' ').trim();
  }

  const parsed = parseNumber(text);
  if (!parsed) return text;

  const displayedValue = parsed.percent ? parsed.value * 100 : parsed.value;
  const percentSuffix = parsed.percent ? '%' : '';

  switch (action) {
    case 'general':
      return `${plainNumber(displayedValue)}${percentSuffix}`;
    case 'zero-decimals':
      return `${fixed(displayedValue, 0)}${percentSuffix}`;
    case 'decrease-decimal':
      return `${fixed(displayedValue, Math.max(0, parsed.decimals - 1))}${percentSuffix}`;
    case 'increase-decimal':
      return `${fixed(displayedValue, Math.min(MAX_DECIMALS, parsed.decimals + 1))}${percentSuffix}`;
    case 'comma':
      return `${withCommas(displayedValue, parsed.decimals)}${percentSuffix}`;
    case 'currency':
      return `$${withCommas(parsed.value, 2)}`;
    case 'percent':
      return `${fixed(parsed.value * 100, Math.max(0, parsed.decimals))}%`;
    case 'multiply-10':
      return plainNumber(parsed.value * 10);
    case 'divide-10':
      return plainNumber(parsed.value / 10);
    default:
      return text;
  }
}

export function applySourceNumberAction(
  grid: string[][],
  cells: SourceGridCell[],
  action: SourceNumberAction,
): string[][] {
  if (!cells.length) return grid;

  const next = grid.map((row) => [...row]);
  for (const { r, c } of cells) {
    if (r < 0 || c < 0) continue;
    while (next.length <= r) next.push([]);
    while (next[r].length <= c) next[r].push('');
    next[r][c] = formatSourceValue(next[r][c] ?? '', action);
  }
  return next;
}

export function formatSourceSelectionLabel(cells: SourceGridCell[]): string {
  if (!cells.length) return 'No selection';

  const rows = cells.map((cell) => cell.r);
  const cols = cells.map((cell) => cell.c);
  const r0 = Math.min(...rows);
  const r1 = Math.max(...rows);
  const c0 = Math.min(...cols);
  const c1 = Math.max(...cols);

  const colName = (index: number) => {
    let value = index + 1;
    let out = '';
    while (value > 0) {
      const remainder = (value - 1) % 26;
      out = String.fromCharCode(65 + remainder) + out;
      value = Math.floor((value - 1) / 26);
    }
    return out;
  };

  const start = `${colName(c0)}${r0 + 1}`;
  const end = `${colName(c1)}${r1 + 1}`;
  const range = start === end ? start : `${start}:${end}`;
  return `${range} · ${cells.length} cell${cells.length === 1 ? '' : 's'}`;
}
