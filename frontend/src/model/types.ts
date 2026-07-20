export type PageType = 'data-grid' | 'canvas' | 'underlay' | 'hybrid' | 'cover' | 'index';

export type BlockType =
  | 'title'
  | 'subtitle'
  | 'paragraph'
  | 'bulletList'
  | 'sectionHeading'
  | 'table'
  | 'matrix'
  | 'excelRange'
  | 'idfNetworkTable'
  | 'imagePlaceholder'
  | 'canvas'
  | 'note'
  | 'cover'
  | 'companyInfo'
  | 'underlayPlaceholder';

export interface BorderSide {
  style?: string;
  color?: string;
}

/** Full per-cell style carried by an excelRange block (keys are "r:c", 0-based). */
export interface ExcelCellStyle {
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  fontSize?: number | null;
  fontName?: string | null;
  fontColor?: string | null;
  hAlign?: string | null;
  vAlign?: string | null;
  wrap?: boolean;
  rotation?: number;
  indent?: number;
  fill?: string | null;
  borders?: {
    top?: BorderSide;
    right?: BorderSide;
    bottom?: BorderSide;
    left?: BorderSide;
  };
}

export interface PageBlock {
  id: string;
  type: BlockType;
  sourceWorksheetId?: string;
  sourceRange?: string;
  sourceSheet?: string;
  text?: string;
  items?: string[];
  headers?: string[];
  rows?: string[][];
  /** Per-cell background fill/highlight, keyed "r:c" (r=-1 is a header cell).
   *  Populated from source workbook fills at import and edited via the table
   *  right-click Highlight actions. Persists in project JSON. */
  cellFills?: Record<string, string>;
  filename?: string;
  styleRole?: string;
  editable?: boolean;
  url?: string;
  /** excelRange payload (exact worksheet range). */
  renderMode?: string;
  renderProfile?: string;
  normalizedHeaderStyle?: string;
  grid?: string[][];
  styles?: Record<string, ExcelCellStyle>;
  mergedCells?: MergedCell[];
  colWidths?: number[];
  rowHeights?: number[];
  /** Absolute worksheet row indices represented by this block (for live refresh
   *  and split-safe editing). */
  srcRows?: number[];
  headerRowCount?: number;
  repeatRows?: number[];
  splitMode?: string;
  minScale?: number;
  allowContinuation?: boolean;
  manualRanges?: number[][];
  layoutWarnings?: string[];
  scaleMode?: string;
  orientation?: string;
  printArea?: string | null;
  bodyRowFillMode?: 'none' | 'source' | 'zebra';
  gridLines?: boolean;
  /** Explicit body font size in px, overriding per-cell Excel font size
   *  (instruction_table / front_matter_narrative_table profiles). */
  bodyFontPx?: number;
  /** Column indices that must not wrap word-by-word (Section labels on
   *  front_matter_narrative_table pages — FINAL SA31 POLISH 4I Phase C). */
  nowrapColumns?: number[];
  preventStackedLabels?: boolean;
  /** Never stretch this excelRange block past its natural size to fill the
   *  page width (instruction_table profile only — FINAL RELEASE CLEANUP
   *  4H+SA38, Phase H). Width-driven grow-to-fill also scales height by the
   *  same factor, which can overflow the page's real safe render area for a
   *  narrow table and silently drop bottom rows in export. */
  noGrow?: boolean;
  /** Optional per-block scale ceiling. Used to keep sibling schedule pages at one visual scale. */
  maxScale?: number;
  /** RDM / IDF network table (idfNetworkTable) payload — TABLE STYLE 4F. */
  layoutMode?: 'single' | 'two_up';
  sectionTitle?: string;
  leftRows?: string[][];
  rightRows?: string[][];
  portRangeLeft?: string;
  portRangeRight?: string;
  fontSize?: number;
  rowHeight?: number;
  headerHeight?: number;
  contentWidth?: number;
  contentHeight?: number;
  sourceRowCount?: number;
  scaledUp?: boolean;
  /** Trailing-blank-range trim diagnostics (FINAL RENDER POLISH 4G, Phase B/I). */
  rowsBeforeTrim?: number;
  colsBeforeTrim?: number;
  rowsAfterTrim?: number;
  colsAfterTrim?: number;
}

export interface CellStyle {
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  fontSize?: number | null;
  hAlign?: string | null;
  vAlign?: string | null;
  fill?: string | null;
  border?: boolean;
}

export interface MergedCell {
  startRow: number;
  startCol: number;
  endRow: number;
  endCol: number;
}

export interface Worksheet {
  id: string;
  name: string;
  grid: string[][];
  /** A1-keyed cell styles (superset used by both source view and exact range). */
  styles?: Record<string, ExcelCellStyle>;
  mergedCells?: MergedCell[];
  rowHeights?: Record<string, number>;
  columnWidths?: Record<string, number>;
  colWidthsPx?: number[];
  rowHeightsPx?: number[];
  sourceSheet?: string;
  sourceRange?: string;
  printArea?: string | null;
}

export interface PageModel {
  id: string;
  order: number;
  include: boolean;
  sheetCode: string;
  displaySheetCode?: string;
  sheetTitle: string;
  sheetTab: string;
  pageType: PageType;
  pageFamily?: string;
  /** Export-visible placeholder note for a blank canvas/drawing/pdf-vector
   *  page with no image content (FINAL RELEASE CLEANUP 4H+SA38, Phase C).
   *  Set by the importer; blank/absent when the page has real image content
   *  or isn't a canvas page. */
  blankPagePlaceholder?: string;
  /** Rendering-options profile: front_matter_table | front_matter_narrative_table
   *  | io_table | network_48_port | instruction_table | company_info. */
  /** Show Terminated By column on RDM/IDF network tables (default hidden). */
  showTerminatedBy?: boolean;
  layoutProfile?: string;
  /** True when a network_48_port page used the two-up (ports 1-N / N+1-total)
   *  side-by-side layout instead of one full-width table. */
  twoUp?: boolean;
  renderMode?: string;
  /** Singh360 render profile + normalized header style (Milestone 4D). */
  renderProfile?: string;
  normalizedHeaderStyle?: 'orange' | 'source' | 'none';
  sourceSheet?: string;
  sourceRange?: string;
  printArea?: string | null;
  splitMode?: string;
  repeatRows?: number[];
  minScale?: number;
  allowContinuation?: boolean;
  scaleMode?: string;
  /** Trim trailing blank worksheet columns/rows from the normalized/export
   *  render only — the Source tab is never affected (FINAL RENDER POLISH
   *  4G, Phase B/H). Both default true. */
  trimBlankRows?: boolean;
  trimBlankColumns?: boolean;
  orientation?: string;
  template?: string;
  templateId: string;
  linkedWorksheetId?: string;
  blocks?: PageBlock[];
  /** Bumped when normalized blocks are rebuilt from source (forces view refresh). */
  sourceRevision?: number;
  canvasObjects: Record<string, unknown>[];
  assets?: Record<string, unknown>[];
  notes: string;
  pageNumber?: number | null;
  pageTotal?: number;
  pageGroupId?: string;
  continuationOf?: string | null;
  continuationIndex?: number;
  generatedContinuation?: boolean;
  layoutWarnings?: string[];
}

export interface ProjectModel {
  id: string;
  metadata: {
    projectName: string;
    storeNumber?: string;
    client?: string;
    location?: string;
    address?: string;
    purpose?: string;
    createdBy?: string;
    createdDate?: string;
    sourceFile?: string;
    version?: string;
    status?: string;
    editedBy?: string;
    date?: string;
    drawnBy?: string;
    checkedBy?: string;
    issueDate?: string;
    revision?: string;
    drawingPackageFileName?: string;
  };
  worksheets: Worksheet[];
  pages: PageModel[];
  sources: Record<string, unknown>[];
  modified?: string;
  projectFolder?: string;
  projectDisplayName?: string;
  sourceWorkbookName?: string;
  paginationLocked?: boolean;
  revisionHistory?: Array<{ revision: string; date: string; description?: string; exportedBy?: string }>;
}

export type ViewMode = 'normalized' | 'source';

export interface CanvasSelection {
  type: string;
  name?: string;
  fill: string;
  stroke: string;
  strokeWidth: number;
  opacity?: number;
  fontSize?: number;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  textAlign?: string;
  isText?: boolean;
  isConnector?: boolean;
  connectorKind?: 'line' | 'arrow' | 'polyline' | 'elbow';
  pointsCount?: number;
  label?: string;
  isImage?: boolean;
  isGroup?: boolean;
  isLegend?: boolean;
  pdfSource?: string;
  pdfPage?: number;
  pdfDpi?: number;
  pdfCrop?: string;
  dash?: string;
  arrowStart?: boolean;
  arrowEnd?: boolean;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  angle?: number;
  locked: boolean;
}

export interface LineStyle {
  stroke: string;
  dash: 'solid' | 'dashed' | 'dotted' | 'dash-dot' | 'long-dash';
  strokeWidth: number;
  arrowStart: boolean;
  arrowEnd: boolean;
}

export interface BusOptions {
  count: number;
  labels: string[];
  presetId: string;
  stroke: string;
  strokeWidth: number;
  dash: 'solid' | 'dashed' | 'dotted' | 'dash-dot' | 'long-dash';
  spacing: number;
  orthogonal: boolean;
}

export interface PdfCropInsertMeta {
  pdfSource: string;
  pdfPage: number;
  pdfDpi: number;
  pdfCrop?: string; // "x0,y0,x1,y1" in PDF points
}

export interface SymbolLegendInsertRow {
  label: string;
  symbolUrl?: string;
  name?: string;
  acronym?: string;
  iconSize?: number;
  category?: string;
  defaultWidth?: number;
  defaultHeight?: number;
}

export interface SymbolLegendInsertConfig {
  title: string;
  rows: SymbolLegendInsertRow[];
}

export interface CanvasApi {
  /** Synchronously read and return the current Fabric canvas serialisation.
   *  Call this before any page-switch or save so you always capture the
   *  live canvas state — React's async setProject may not have committed
   *  the latest changes to projectRef yet. */
  captureCanvas: () => Record<string, unknown>[];
  addText: () => void;
  addRect: () => void;
  addCircle: () => void;
  addLine: () => void;
  addArrow: () => void;
  addPolyline: () => void;
  addElbow: () => void;
  addBracket: () => void;
  addDashedBox: () => void;
  setLineStyle: (style: LineStyle) => void;
  startBus: (opts: BusOptions) => void;
  addImage: (url: string, name?: string, at?: { clientX: number; clientY: number }) => void;
  addPdfCrop: (url: string, name: string, opts?: { underlay?: boolean; meta?: PdfCropInsertMeta }) => void;
  addComponent: (
    url: string,
    name: string,
    label: string | null,
    at?: { clientX: number; clientY: number },
    meta?: { category?: string; defaultWidth?: number; defaultHeight?: number; acronym?: string },
  ) => void;
  addComponentPair: (sourceUrl: string, symbolUrl: string, name: string, label: string | null, at?: { clientX: number; clientY: number }) => void;
  addLegend: (presetIds?: string[]) => void;
  addSymbolLegend: (config: SymbolLegendInsertConfig) => void;
  normalizeSymbolSize: () => void;
  addPageTitle: (text: string) => void;
  addSectionHeader: (text: string) => void;
  addNote: (text: string) => void;
  deleteSelected: () => void;
  copySelected: () => void;
  pasteCopied: () => void;
  duplicateSelected: () => void;
  unlockAll: () => void;
  undo: () => void;
  redo: () => void;
  group: () => void;
  ungroup: () => void;
  bringForward: () => void;
  sendBackward: () => void;
  bringToFront: () => void;
  sendToBack: () => void;
  alignObjects: (direction: 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom' | 'page-center-h' | 'page-center-v') => void;
  distributeObjects: (direction: 'horizontal' | 'vertical') => void;
  matchObjectSize: (which: 'width' | 'height' | 'both') => void;
  updateSelected: (patch: Partial<CanvasSelection>) => void;
  reverseConnectorDirection: () => void;
  addVertexToSelected: () => void;
  deleteVertexFromSelected: () => void;
  convertSelectedConnector: (kind: 'line' | 'arrow' | 'polyline' | 'elbow') => void;
}
