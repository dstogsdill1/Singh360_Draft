export interface ClipboardCell {
  value: string;
  formula?: string;
  style?: Record<string, string | boolean>;
  rowSpan?: number;
  colSpan?: number;
}

export function parseClipboard(html: string, plain: string): ClipboardCell[][] {
  if (!html.trim()) return plain.replace(/\r/g, '').split('\n').filter((row, index, all) => row || index < all.length - 1).map((row) => row.split('\t').map((value) => ({ value })));
  const document = new DOMParser().parseFromString(html, 'text/html');
  const rows = Array.from(document.querySelectorAll('tr'));
  return rows.map((row) => Array.from(row.querySelectorAll('th,td')).map((cell) => {
    const computed = (cell as HTMLElement).style;
    return {
      value: cell.textContent || '',
      formula: cell.getAttribute('data-formula') || undefined,
      rowSpan: Number(cell.getAttribute('rowspan') || 1),
      colSpan: Number(cell.getAttribute('colspan') || 1),
      style: {
        ...(computed.backgroundColor ? { fill: computed.backgroundColor } : {}),
        ...(computed.color ? { color: computed.color } : {}),
        ...(computed.fontFamily ? { fontFamily: computed.fontFamily } : {}),
        ...(computed.fontSize ? { fontSize: computed.fontSize } : {}),
        ...(computed.fontWeight ? { bold: computed.fontWeight === 'bold' || Number(computed.fontWeight) >= 600 } : {}),
        ...(computed.fontStyle ? { italic: computed.fontStyle === 'italic' } : {}),
        ...(computed.textDecoration ? { underline: computed.textDecoration.includes('underline') } : {}),
        ...(computed.textAlign ? { horizontalAlign: computed.textAlign } : {}),
        ...(computed.verticalAlign ? { verticalAlign: computed.verticalAlign } : {}),
        ...(computed.whiteSpace ? { wrap: computed.whiteSpace !== 'nowrap' } : {}),
        ...(computed.border ? { border: computed.border } : {}),
        ...(cell.getAttribute('data-number-format') ? { numberFormat: cell.getAttribute('data-number-format') || '' } : {}),
      },
    };
  }));
}

export function clipboardPayload(rows: ClipboardCell[][]): { html: string; plain: string } {
  const plain = rows.map((row) => row.map((cell) => cell.formula || cell.value).join('\t')).join('\n');
  const html = `<table>${rows.map((row) => `<tr>${row.map((cell) => `<td${cell.rowSpan && cell.rowSpan > 1 ? ` rowspan="${cell.rowSpan}"` : ''}${cell.colSpan && cell.colSpan > 1 ? ` colspan="${cell.colSpan}"` : ''}>${cell.value.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</td>`).join('')}</tr>`).join('')}</table>`;
  return { html, plain };
}
