import type { ExcelCellStyle, PageBlock } from './types';

const text = (value: unknown): string => String(value ?? '').trim();
const key = (value: unknown): string => text(value).toLowerCase();

function headerRowIndex(grid: string[][]): number {
  if (grid.length >= 4 && (grid[3] ?? []).some((value) => text(value))) return 3;
  const found = grid.slice(0, 20).findIndex(
    (row) => row.filter((value) => text(value)).length >= 2,
  );
  return Math.max(0, found);
}

function headerColumn(headers: string[], name: string): number {
  return headers.findIndex((header) => key(header) === key(name));
}

function rowValue(row: string[], headers: string[], name: string): string {
  const index = headerColumn(headers, name);
  return index >= 0 ? text(row[index]) : '';
}

function uniqueJoin(values: string[], keepTbd = true): string {
  const output: string[] = [];
  values.forEach((raw) => {
    const value = text(raw).replace(/\s+/g, ' ');
    if (!value || value === '-') return;
    if (!keepTbd && ['tbd', 'verify'].includes(value.toLowerCase())) return;
    if (!output.some((item) => item.toLowerCase() === value.toLowerCase())) output.push(value);
  });
  return output.join(', ');
}

function projectBlock(
  base: PageBlock,
  title: string,
  subtitle: string,
  headers: string[],
  rows: string[][],
  sourceHeaders: string[],
  sourceNames: string[],
): PageBlock {
  const sourceGrid = base.grid ?? [];
  const sourceHeaderRow = headerRowIndex(sourceGrid);
  const sourceColumns = sourceNames.map((name) => headerColumn(sourceHeaders, name));
  const sourceStyles = base.styles ?? {};
  const styles: Record<string, ExcelCellStyle> = {};

  const copyStyle = (
    newRow: number,
    newColumn: number,
    oldRow: number,
    oldColumn: number,
  ): void => {
    const exact = sourceStyles[`${oldRow}:${oldColumn}`];
    const fallback = sourceStyles[`${oldRow}:0`];
    const style = exact ?? fallback;
    if (style) styles[`${newRow}:${newColumn}`] = { ...style };
  };

  [0, 1, 2, sourceHeaderRow].forEach((oldRow, newRow) => {
    sourceColumns.forEach((oldColumn, newColumn) => {
      copyStyle(newRow, newColumn, oldRow, Math.max(0, oldColumn));
    });
  });
  rows.forEach((_row, offset) => {
    sourceColumns.forEach((oldColumn, newColumn) => {
      copyStyle(4 + offset, newColumn, sourceHeaderRow + 1, Math.max(0, oldColumn));
    });
  });

  const colWidths = sourceColumns.map((oldColumn, index) => {
    if (oldColumn >= 0 && base.colWidths?.[oldColumn]) return base.colWidths[oldColumn];
    return Math.max(76, Math.min(220, 16 + headers[index].length * 8));
  });
  const width = Math.max(1, headers.length);
  const grid = [
    [title, ...Array(Math.max(0, width - 1)).fill('')],
    [subtitle, ...Array(Math.max(0, width - 1)).fill('')],
    Array(width).fill(''),
    [...headers],
    ...rows.map((row) => [
      ...row.slice(0, width),
      ...Array(Math.max(0, width - row.length)).fill(''),
    ]),
  ];

  return {
    ...base,
    grid,
    styles,
    mergedCells: [],
    colWidths,
    rowHeights: [28, 22, 10, 24, ...rows.map(() => 22)],
    srcRows: grid.map((_row, index) => index),
    headerRowCount: 4,
    repeatRows: [0, 1, 2, 3],
    dataRowCount: rows.length,
  };
}

function rackRowMatches(row: string[], headers: string[], rack: string): boolean {
  const letter = text(rack).toUpperCase();
  if (!['A', 'B', 'C'].includes(letter)) return false;
  return ['Panel ID', 'I/O Group', 'Device / Case', 'Description'].some((name) => {
    const compact = rowValue(row, headers, name).toUpperCase().replace(/[^A-Z0-9]+/g, '');
    return [letter, `R${letter}`, `RACK${letter}`].includes(compact)
      || compact.startsWith(`RACK${letter}`)
      || (compact.startsWith(`R${letter}`) && !compact.startsWith('RACK'));
  });
}

export function applyCanonicalView(
  base: PageBlock,
  view: string,
  filterValue = '',
): PageBlock {
  const grid = base.grid ?? [];
  const sourceHeaderRow = headerRowIndex(grid);
  const headers = (grid[sourceHeaderRow] ?? []).map(text);
  const rows = grid
    .slice(sourceHeaderRow + 1)
    .filter((row) => row.some((value) => text(value)))
    .map((row) => row.map(text));
  const select = (row: string[], names: string[]): string[] => (
    names.map((name) => rowValue(row, headers, name))
  );

  if (view === 'network_summary') {
    const grouped = new Map<string, { idf: string; networkSwitch: string; rows: string[][] }>();
    rows.forEach((row) => {
      const idf = rowValue(row, headers, 'IDF');
      const networkSwitch = rowValue(row, headers, 'Switch');
      const groupKey = `${idf}\u0000${networkSwitch}`;
      const group = grouped.get(groupKey) ?? { idf, networkSwitch, rows: [] };
      group.rows.push(row);
      grouped.set(groupKey, group);
    });
    const summary = [...grouped.values()]
      .sort((a, b) => (
        a.idf.localeCompare(b.idf, undefined, { numeric: true })
        || a.networkSwitch.localeCompare(b.networkSwitch, undefined, { numeric: true })
      ))
      .map((group) => {
        const spare = group.rows.filter((row) => {
          const marker = `${rowValue(row, headers, 'Label')} ${rowValue(row, headers, 'Device / Drop')}`
            .toLowerCase();
          return !marker.trim() || marker.includes('spare') || marker.includes('placeholder');
        }).length;
        return [
          group.idf,
          group.networkSwitch,
          String(group.rows.length),
          String(group.rows.length - spare),
          String(spare),
          uniqueJoin(group.rows.map((row) => rowValue(row, headers, 'Network'))),
          uniqueJoin(group.rows.map((row) => rowValue(row, headers, 'Status'))),
        ];
      });
    const outputHeaders = ['IDF', 'Switch', 'Port Count', 'Assigned', 'Spare / TBD', 'Network', 'Status'];
    return projectBlock(
      base,
      'NETWORK / WICP SUMMARY',
      'Port totals summarized by IDF and switch; detailed ports remain on EMS 13.1–13.3.',
      outputHeaders,
      summary,
      headers,
      ['IDF', 'Switch', 'Port', 'Label', 'Label', 'Network', 'Status'],
    );
  }

  if (view === 'wicp_count_summary') {
    const wicpRows = rows.filter((row) => (
      key(rowValue(row, headers, 'Panel Type')) === 'wicp'
      || key(rowValue(row, headers, 'Panel ID')).startsWith('wicp')
    ));
    const summary = wicpRows.length
      ? [[
        'WICP',
        String(wicpRows.length),
        uniqueJoin(wicpRows.map((row) => rowValue(row, headers, 'Panel ID'))),
        uniqueJoin(wicpRows.map((row) => rowValue(row, headers, 'Location')), false) || 'TBD',
        uniqueJoin(wicpRows.map((row) => rowValue(row, headers, 'Status'))),
      ]]
      : [];
    const outputHeaders = ['Panel Type', 'Count', 'Panel IDs', 'Location', 'Status'];
    return projectBlock(
      base,
      'WICP COUNT SUMMARY',
      'Panel/count data from 22_PANELS only.',
      outputHeaders,
      summary,
      headers,
      ['Panel Type', 'Panel ID', 'Panel ID', 'Location', 'Status'],
    );
  }

  if (view === 'rack_io' || view === 'wicp_io') {
    const filtered = view === 'rack_io'
      ? rows.filter((row) => rackRowMatches(row, headers, filterValue))
      : rows.filter((row) => key(rowValue(row, headers, 'Panel ID')).startsWith('wicp'));
    const names = [
      'Panel ID',
      'Controller ID',
      'I/O Group',
      'Point No.',
      'Point Type',
      'Point Label',
      'Description',
      'Device / Case',
      'Cable / Terminal',
      'Status',
    ];
    const rack = text(filterValue).toUpperCase();
    return projectBlock(
      base,
      view === 'rack_io' ? `RACK ${rack} I/O SCHEDULE` : 'WICP I/O SCHEDULE',
      view === 'rack_io'
        ? `I/O rows from 23_PANEL_IO filtered to Rack ${rack}.`
        : 'I/O rows from 23_PANEL_IO only.',
      names,
      filtered.map((row) => select(row, names)),
      headers,
      names,
    );
  }

  if (view === 'case_controllers') {
    const filtered = rows.filter((row) => {
      const marker = [
        'Controller ID',
        'Controller Label',
        'Controller Type',
        'Panel / Location',
      ].map((name) => rowValue(row, headers, name)).join(' ').toLowerCase();
      const controllerId = rowValue(row, headers, 'Controller ID').toUpperCase();
      return marker.includes('case') || marker.includes('refrig') || controllerId.startsWith('CC');
    });
    const names = [
      'Controller ID',
      'Controller Label',
      'Controller Type',
      'Panel / Location',
      'Network / IDF',
      'IP Address',
      'Source ID',
      'Status',
      'Notes',
    ];
    return projectBlock(
      base,
      'CASE CONTROLLER SCHEDULE',
      'Case-controller records from 20_CONTROLLERS only.',
      names,
      filtered.map((row) => select(row, names)),
      headers,
      names,
    );
  }

  const lighting: Record<string, { title: string; subtitle: string; names: string[] }> = {
    lighting_matrix: {
      title: 'LIGHTING OUTPUT MATRIX',
      subtitle: 'All lighting outputs organized by zone, area, schedule, and point.',
      names: [
        'Output / Zone',
        'Description',
        'Area / Fixture Group',
        'Schedule / Time',
        'Output Type',
        'Panel',
        'Point',
        'Status',
      ],
    },
    lighting_io: {
      title: 'LIGHTING TDB I/O SCHEDULE',
      subtitle: 'Controller, panel, and point view from 26_LIGHTING_OUTPUTS.',
      names: [
        'Controller ID',
        'Panel',
        'Point',
        'Output Type',
        'Output / Zone',
        'Description',
        'Source ID',
        'Status',
      ],
    },
    lighting_dimming: {
      title: 'LIGHTING CONTROL / DIMMING SCHEDULE',
      subtitle: 'Dimming and analog-control outputs from 26_LIGHTING_OUTPUTS.',
      names: [
        'Output / Zone',
        'Output Type',
        'Description',
        'Area / Fixture Group',
        'Schedule / Time',
        'Controller ID',
        'Panel',
        'Point',
        'Status',
        'Notes',
      ],
    },
  };
  const lightingView = lighting[view];
  if (lightingView) {
    const filtered = view === 'lighting_dimming'
      ? rows.filter((row) => {
        const outputType = key(rowValue(row, headers, 'Output Type'));
        const output = rowValue(row, headers, 'Output / Zone').toUpperCase();
        const point = rowValue(row, headers, 'Point').toUpperCase();
        return outputType.includes('dimm')
          || output.startsWith('D')
          || point.startsWith('AI')
          || point.startsWith('AO');
      })
      : rows;
    return projectBlock(
      base,
      lightingView.title,
      lightingView.subtitle,
      lightingView.names,
      filtered.map((row) => select(row, lightingView.names)),
      headers,
      lightingView.names,
    );
  }

  return base;
}
