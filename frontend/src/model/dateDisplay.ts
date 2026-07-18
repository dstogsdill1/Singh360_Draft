const MS_PER_DAY = 86_400_000;
const EXCEL_EPOCH_UTC = Date.UTC(1899, 11, 30);

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

function formatParts(year: number, month: number, day: number): string {
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return '';
  return `${pad2(month)}/${pad2(day)}/${year}`;
}

function fromExcelSerial(serial: number): string {
  if (!Number.isFinite(serial) || serial <= 0 || serial > 100_000) return '';
  const date = new Date(EXCEL_EPOCH_UTC + Math.floor(serial) * MS_PER_DAY);
  return formatParts(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

/**
 * Convert imported Excel/ISO/JavaScript date values to a stable date-only label.
 * Deliberately avoids local-time conversion for ISO timestamps so an issue date
 * never shifts backward/forward a day because of the browser timezone.
 */
export function formatDateOnly(value: unknown): string {
  if (value == null) return '';
  if (value instanceof Date && Number.isFinite(value.getTime())) {
    return formatParts(value.getFullYear(), value.getMonth() + 1, value.getDate());
  }

  const raw = String(value).trim();
  if (!raw || raw === '—') return '';

  const numeric = Number(raw);
  if (Number.isFinite(numeric)) {
    const excel = fromExcelSerial(numeric);
    if (excel) return excel;
    if (numeric > 10_000_000_000) {
      const date = new Date(numeric);
      if (Number.isFinite(date.getTime())) {
        return formatParts(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
      }
    }
  }

  const iso = /^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/.exec(raw);
  if (iso) return formatParts(Number(iso[1]), Number(iso[2]), Number(iso[3]));

  const mdy = /^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})(?:\s+.*)?$/.exec(raw);
  if (mdy) {
    const year = Number(mdy[3]) < 100 ? 2000 + Number(mdy[3]) : Number(mdy[3]);
    return formatParts(year, Number(mdy[1]), Number(mdy[2]));
  }

  const dotNet = /^\/Date\((\d+)\)\/$/.exec(raw);
  if (dotNet) {
    const date = new Date(Number(dotNet[1]));
    if (Number.isFinite(date.getTime())) {
      return formatParts(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
    }
  }

  const parsed = new Date(raw);
  if (Number.isFinite(parsed.getTime())) {
    return formatParts(parsed.getFullYear(), parsed.getMonth() + 1, parsed.getDate());
  }

  // Last-resort cleanup: remove obvious timestamp suffixes without inventing a date.
  return raw.replace(/[T\s]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/i, '');
}
