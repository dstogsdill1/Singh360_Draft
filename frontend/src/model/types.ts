export type PageType = 'data-grid' | 'canvas' | 'underlay' | 'hybrid' | 'cover' | 'index' | 'pdf' | 'image' | 'text';

export interface ExcelLayoutStyle {
  fill?: string;
  fontColor?: string;
  fontSize?: number;
  bold?: boolean;
  align?: 'left' | 'center' | 'right';
  wrap?: boolean;
  borderColor?: string;
  borderStyle?: 'none' | 'thin' | 'medium';
}

export interface ExcelLayoutMerge {
  startRow: number;
  startCol: number;
  endRow: number;
  endCol: number;
}

export interface ExcelLayoutTable {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rows: string[][];
  columnWidths: number[];
  rowHeights: number[];
  merges: ExcelLayoutMerge[];
  title: string;
  titleStyle: ExcelLayoutStyle;
  headerStyle: ExcelLayoutStyle;
  bodyStyle: ExcelLayoutStyle;
  alternatingFill?: string;
  keepTogether: boolean;
  splitRows: boolean;
  repeatTitle: boolean;
  repeatHeaders: boolean;
  /** Per-cell styling from Excel/Google Sheets HTML, keyed "row:column". */
  cellStyles?: Record<string, ExcelLayoutStyle>;
}

export interface ExcelLayoutModel {
  version: 1;
  pageWidth: number;
  pageHeight: number;
  printableMargin: number;
  snapSize: number;
  tabColor?: string | null;
  tables: ExcelLayoutTable[];
}

export type SpreadsheetFitMode = 'fit_width' | 'fit_box' | 'exact_scale';
export type SpreadsheetOverflowMode = 'visible' | 'clip' | 'explicit_continuation';

export interface DrawingMaskRange {
  range: string;
}

/** Stable, user-authored placement of one exact worksheet range on one page. */
export interface SpreadsheetRegion {
  id: string;
  sourceSheetId: string;
  range: string;
  pageId: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fitMode: SpreadsheetFitMode;
  overflowMode: SpreadsheetOverflowMode;
  /** Absolute, zero-based worksheet rows. Nothing is repeated unless listed. */
  repeatRows: number[];
  /** Absolute, zero-based worksheet row boundaries selected by the user. */
  explicitBreaks: number[];
  preserveGeometry: boolean;
  scale: number;
  continuationOf?: string;
}

export interface SpreadsheetPageRecipe {
  pageId: string;
  regions: SpreadsheetRegion[];
}

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
  numberFormat?: string | null;
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
  /** Cover is bound to selected 00_PROJECT_META fields, not raw recipe rows. */
  metadataBound?: boolean;
  /** Published table comes from the canonical workbook data contract. */
  canonicalDataSource?: boolean;
  canonicalSourceSheet?: string;
  canonicalView?: string;
  canonicalViewFilter?: string;
  dataRowCount?: number;
  sourceFilter?: { column: string; value: string };
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
  preserveGeometry?: boolean;
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
  /** Actual vertical render budget after page band and title-block safety gap. */
  safeBodyHeight?: number;
  heightSafetyFactor?: number;
  /** Optional per-block scale ceiling. Used to keep sibling schedule pages at one visual scale. */
  maxScale?: number;
  /** RDM / IDF network table (idfNetworkTable) payload — TABLE STYLE 4F. */
  layoutMode?: 'single' | 'two_up';
  /** S360_HEB_IDF_SWITCH_MATRIX_V1 — exact schema; H-E-B uses seven source columns only. */
  tableProfile?: string;
  leftCaption?: string;
  rightCaption?: string;
  pageCount?: number;
  pairIndex?: number;
  switchKeys?: string[];
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
  visible?: boolean;
  grid: string[][];
  /** A1-keyed cell styles (superset used by both source view and exact range). */
  styles?: Record<string, ExcelCellStyle>;
  formulas?: Record<string, string>;
  mergedCells?: MergedCell[];
  /** Explicit Excel row heights in points and column widths in OOXML units. */
  rowHeights?: Record<string, number>;
  columnWidths?: Record<string, number>;
  defaultColumnWidth?: number;
  defaultRowHeight?: number;
  geometryAuthority?: 'workbook-v1';
  colWidthsPx?: number[];
  rowHeightsPx?: number[];
  tabColor?: string | null;
  /** App-only visibility. These never alter the original Excel workbook. */
  hiddenRows?: number[];
  hiddenColumns?: number[];
  /** Hidden cell coordinates use zero-based "row:column" keys. */
  hiddenCells?: string[];
  sourceSheet?: string;
  sourceRange?: string;
  printArea?: string | null;
  role?: string | null;
  sourceSetup?: {
    authority?: string;
    sheetCode?: string;
    title?: string;
    pageType?: string;
    publish?: '' | 'YES' | 'NO' | 'VERIFY';
    purpose?: string;
    instruction?: string;
    editableStartRow?: number;
    metadata?: Array<{ field: string; value: string; notes: string }>;
  };
  protectedRanges?: string[];
  dataValidations?: Array<Record<string, unknown>>;
  conditionalFormats?: Array<Record<string, unknown>>;
  tableRegions?: Array<{ id: string; range: string; label: string }>;
  tableLayout?: 'single' | 'side_by_side' | 'stacked';
  annotations?: Array<{
    id: string;
    text: string;
    placement: 'right' | 'bottom';
  }>;
  /** Explicit Data Workspace page recipes. Legacy auto-layout remains intact
   * until a user creates one of these recipes. */
  pageLayouts?: SpreadsheetPageRecipe[];
}

export type PageIssueStatus = 'draft' | 'draft_confirmed' | 'public' | 'public_confirmed';

export interface PageModel {
  id: string;
  order: number;
  /** Original package slot retained while a page is excluded. */
  restorePackageIndex?: number;
  include: boolean;
  /** Only an explicit YES publishes; NO, VERIFY, and blank stay editable. */
  publishStatus?: '' | 'YES' | 'NO' | 'VERIFY';
  /** Four-stage issue workflow. Include/Exclude remains separate. */
  issueStatus?: PageIssueStatus;
  statusUpdatedAt?: string;
  statusConfirmedAt?: string;
  parentPageId?: string;
  sourceMode?: string;
  syncDirection?: string;
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
  /** Semantic spreadsheet arrangement; recomposed by the server when changed. */
  layoutOverride?: 'auto' | 'exact_source' | 'one_column' | 'two_columns' | 'continue_blocks' | 'keep_one_page';
  layoutDiagnostics?: Record<string, unknown>;
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
  createdAt?: string;
  modifiedAt?: string;
  archivedAt?: string;
  archivedReason?: string;
  archivedFromIndex?: number;
  archivedPreviousPageId?: string;
  archivedNextPageId?: string;
  archivedInclude?: boolean;
  archivedGroupRootId?: string;
  lastArchivedAt?: string;
  lastArchivedReason?: string;
  lastArchivedFromIndex?: number;
  lastArchivedGroupRootId?: string;
  restoredAt?: string;
  managedPage?: 'cover' | 'index';
  appManaged?: boolean;
  standaloneIndex?: boolean;
  indexContinuation?: boolean;
  generatedIndexContinuation?: boolean;
  sourceImport?: {
    id?: string;
    groupId?: string;
    importId?: string;
    importGroupId?: string;
    type: 'pdf' | 'image' | 'xlsx' | 'xlsm' | 'csv' | 'text' | string;
    originalName?: string;
    originalFileName?: string;
    originalPath?: string;
    sha256: string;
    localAsset?: string;
    sourceId?: string;
    projectLocalPath?: string;
    sourcePageIndex?: number;
    sourcePageNumber?: number;
    renderAssetPath?: string;
    renderAssetUrl?: string;
    renderDpi?: number;
    selectedPage?: number;
    pageIndex?: number;
    pageFingerprint?: string;
    selectedWorksheet?: string;
    placementMode?: 'full_sheet' | 'fit_body' | string;
    importedAt: string;
    revision?: number;
    previousSourceId?: string;
    previousSha256?: string;
    previousPageIndex?: number;
  };
  pdfPlacementMode?: 'full_sheet' | 'fit_body';
  suppressTitleBlock?: boolean;
  pageNumber?: number | null;
  pageTotal?: number;
  pageGroupId?: string;
  continuationOf?: string | null;
  continuationIndex?: number;
  generatedContinuation?: boolean;
  indexRowsOnPage?: number;
  indexRowsPerPage?: number;
  indexPageCount?: number;
  layoutWarnings?: string[];
  tableLayout?: 'single' | 'side_by_side' | 'stacked';
  tableAnnotations?: Array<{
    id: string;
    text: string;
    placement: 'right' | 'bottom';
  }>;
  /** Opt-in independent editable tables positioned on stacked 17 x 11 sheets. */
  excelLayout?: ExcelLayoutModel;
  /** Authoritative source-range recipe; bypasses normalized/reflow blocks. */
  spreadsheetRegions?: SpreadsheetRegion[];
  /** Explicit drawing/print area shown in Spreadsheet view (e.g. "A1:F20"). */
  drawingRange?: string;
  /** Render-only column exclusions for Drawing/Preview/PDF (0-based worksheet columns). */
  drawingExcludedColumns?: number[];
  /** Render-only row exclusions for Drawing/Preview/PDF (0-based worksheet rows). */
  drawingExcludedRows?: number[];
  /** Render-only masked cell ranges for Drawing/Preview/PDF (A1 ranges). */
  drawingMaskedRanges?: DrawingMaskRange[];
  /** Placement settings for the page-local spreadsheet drawing renderer. */
  pageLocalPlacement?: {
    fitMode: 'fit_width' | 'fit_box' | 'exact_scale';
    scale?: number;
    hAlign?: 'left' | 'center' | 'right';
    vAlign?: 'top' | 'center' | 'bottom';
  };
}

export interface ProjectModel {
  id: string;
  schemaVersion?: number;
  projectMode?: 'standalone_layout' | string;
  managedPagePolicy?: 'automatic' | 'preserve_existing';
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
    templateVersion?: string;
    status?: string;
    helpVersion?: string;
    editedBy?: string;
    date?: string;
    drawnBy?: string;
    checkedBy?: string;
    issueDate?: string;
    revision?: string;
    drawingPackageFileName?: string;
    projectType?: string;
    drawingSetTitle?: string;
    preparedBy?: string;
    notes?: string;
    customerLogoAsset?: string;
  };
  worksheets: Worksheet[];
  pages: PageModel[];
  sources: Record<string, unknown>[];
  modified?: string;
  /** Timestamp written by ProjectStore after a confirmed local save. */
  lastSavedAt?: string;
  projectFolder?: string;
  projectRoot?: string;
  linkedProjectRoot?: string;
  projectFilesMode?: 'EXACT_LINKED_PROJECT_ROOT' | string;
  projectDisplayName?: string;
  projectProfile?: 'ems';
  sourceWorkbookName?: string;
  paginationLocked?: boolean;
  archived?: boolean;
  archivedAt?: string;
  archivedReason?: string;
  archivedPages?: PageModel[];
  legacyWorkbookReference?: Record<string, unknown>;
  coverSettings?: Record<string, unknown>;
  indexSettings?: Record<string, unknown>;
  workbookSync?: {
    state?: string;
    status?: string;
    mode?: string;
    workbook?: string;
    lastSyncUtc?: string;
    workbookHash?: string;
    appHash?: string;
    warning?: string;
    pendingReason?: string;
    localProjectSavedAt?: string;
    lastAuthorityAction?: string;
    verified?: boolean;
    verification?: {
      status?: string;
      verified?: boolean;
      basePageCount?: number;
      physicalDrawingSheetCount?: number;
      dataWorkspaceDrawingSheetCount?: number;
      verifiedAt?: string;
    };
  };
  dataWorkspace?: {
    revision?: number;
    signature?: string;
    savedAt?: string;
    appliedRevision?: number;
  };
  revisionHistory?: Array<{ revision: string; date: string; description?: string; exportedBy?: string }>;
  savedAssemblies?: SavedAssembly[];
}

export interface SavedAssembly {
  id: string;
  name: string;
  createdAt: string;
  object: Record<string, unknown>;
  category?: string;
  favorite?: boolean;
}

export type CalloutFamily = 'round' | 'square' | 'block';
export type CalloutLayout = 'horizontal' | 'vertical' | 'grid';
export type CalloutMarkerShape = 'round' | 'square' | 'pill' | 'none';

export interface CalloutEntry {
  callout: string;
  label: string;
  description: string;
  /** Legacy serialized description retained for backward-compatible project loads. */
  text?: string;
}

export interface CalloutSetConfig {
  kind: 'callout-set';
  family: CalloutFamily;
  setName: string;
  title: string;
  entries: CalloutEntry[];
  markerShape: CalloutMarkerShape;
  layout: CalloutLayout;
  gridColumns: number;
  markerSize: number;
  spacing: number;
  fill: string;
  stroke: string;
  textColor: string;
}

export interface LibraryComponentInsertMeta {
  category?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  acronym?: string;
  libraryComponentId?: string;
  collection?: string;
  favorite?: boolean;
}

export interface PlacedSymbolEditorConfig {
  name: string;
  label: string;
  width: number;
  height: number;
  category: string;
  opacity: number;
  favorite: boolean;
}

export type SmartComponentType =
  | 'panel-enclosure'
  | 'contactor-bank'
  | 'relay-bank'
  | 'power-monitor-pack'
  | 'terminal-bank'
  | 'labeled-device';

export type SmartBankLayout = 'horizontal' | 'vertical' | 'grid';

export interface SmartPanelEnclosureConfig {
  kind: 'panel-enclosure';
  panelType: 'WICP' | 'LCP' | 'PCP' | 'CCP' | 'REMS' | 'CUSTOM';
  customPanelType: string;
  title: string;
  width: number;
  height: number;
  header: string;
  deviceRows: number;
  deviceColumns: number;
  deviceLabels: string[];
}

export interface SmartContactorBankConfig {
  kind: 'contactor-bank';
  prefix: string;
  startNumber: number;
  numberedCount: number;
  spareCount: number;
  spareLabel: string;
  customLabels: string[];
  /** Automatically derived from custom labels or numbered + spare counts. */
  quantity: number;
  physicalPoles: '1P' | '2P' | '3P';
  scheduledPoles: string;
  layout: SmartBankLayout;
  gridColumns: number;
  spacing: number;
  autoNumber: boolean;
}

export interface SmartRelayBankConfig {
  kind: 'relay-bank';
  prefix: string;
  startNumber: number;
  quantity: number;
  layout: SmartBankLayout;
  gridColumns: number;
  spacing: number;
  autoNumber: boolean;
}

export interface SmartPowerMonitorPackConfig {
  kind: 'power-monitor-pack';
  model: 'PS48' | 'PS24' | 'PS12' | 'PS3';
  mount: 'WALL' | 'DIN';
  terminalBank: string;
  customTerminalBank: string;
  ctQuantity: number;
  ctType: 'Split-core' | 'Solid-core' | 'Rogowski' | 'Custom';
  customCtType: string;
}

export interface SmartTerminalBankConfig {
  kind: 'terminal-bank';
  label: string;
  prefix: string;
  startNumber: number;
  quantity: number;
  layout: 'horizontal' | 'vertical';
  spacing: number;
}

export interface SmartLabeledDeviceConfig {
  kind: 'labeled-device';
  label: string;
  secondaryLabel: string;
  width: number;
  height: number;
  terminalCount: number;
}

export type SmartComponentConfig =
  | SmartPanelEnclosureConfig
  | SmartContactorBankConfig
  | SmartRelayBankConfig
  | SmartPowerMonitorPackConfig
  | SmartTerminalBankConfig
  | SmartLabeledDeviceConfig;

export type QuickAssemblyId =
  | 'signage-marker-trio'
  | 'signage-legend'
  | 'callout-block'
  | 'generated-symbol-key'
  | 'wicp-annotation-pack';

/** 'spreadsheet' = page-local Univer editor for this page's linkedWorksheetId. */
export type ViewMode = 'normalized' | 'source' | 'spreadsheet' | 'print';

export interface CanvasSelection {
  /** S360 POWERPOINT TEXT BOX FORMATTING V1 */
  isTextBox?: boolean;
  textBoxFill?: string;
  textBoxFillOpacity?: number;
  textBoxStroke?: string;
  textBoxStrokeWidth?: number;
  textBoxPadding?: number;
  textBoxRadius?: number;
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
  text?: string;
  isConnector?: boolean;
  connectorKind?: 'line' | 'arrow' | 'polyline' | 'elbow';
  pointsCount?: number;
  label?: string;
  isImage?: boolean;
  isGroup?: boolean;
  isLegend?: boolean;
  smartComponentType?: SmartComponentType;
  smartConfig?: SmartComponentConfig;
  calloutConfig?: CalloutSetConfig;
  sourceUrl?: string;
  symbolLabel?: string;
  symCategory?: string;
  libraryComponentId?: string;
  favorite?: boolean;
  isPlacedSymbol?: boolean;
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

export interface ImageCropRect {
  /** Normalized 0-1 source-image crop rectangle. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export type ImageCropPlacement = 'keep' | 'fit' | 'fill';

export interface ImageCropState {
  sourceUrl: string;
  name: string;
  naturalWidth: number;
  naturalHeight: number;
  crop: ImageCropRect;
  locked: boolean;
}

export interface SymbolLegendInsertRow {
  code?: string;
  glyph?: string;
  shape?: 'circle' | 'square' | 'none';
  color?: string;
  color2?: string;
  pattern?: 'solid' | 'outline' | 'double-outline' | 'split-vertical' | 'split-horizontal' | 'diagonal' | 'crosshatch';
  highlighted?: boolean;
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
  highlighted?: boolean;
  columns?: 1 | 2;
  markerSize?: number;
  frame?: boolean;
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
  addPdfCrop: (url: string, name: string, opts?: { underlay?: boolean; opacity?: number; meta?: PdfCropInsertMeta }) => Promise<void> | void;
  getSelectedImageCrop: () => ImageCropState | null;
  applySelectedImageCrop: (crop: ImageCropRect, placement?: ImageCropPlacement) => void;
  resetSelectedImageCrop: () => void;
  addComponent: (
    url: string,
    name: string,
    label: string | null,
    at?: { clientX: number; clientY: number },
    meta?: LibraryComponentInsertMeta,
  ) => Promise<void>;
  addComponentPair: (sourceUrl: string, symbolUrl: string, name: string, label: string | null, at?: { clientX: number; clientY: number }) => void;
  addLegend: (presetIds?: string[]) => void;
  addSymbolLegend: (config: SymbolLegendInsertConfig) => void;
  addQuickAssembly: (kind: QuickAssemblyId) => Promise<void> | void;
  addSmartComponent: (config: SmartComponentConfig) => void;
  updateSelectedSmartComponent: (config: SmartComponentConfig) => void;
  addCalloutSet: (config: CalloutSetConfig) => void;
  updateSelectedCalloutSet: (config: CalloutSetConfig) => void;
  updateSelectedPlacedSymbol: (config: PlacedSymbolEditorConfig) => void;
  captureSelectedAssembly: () => Record<string, unknown> | null;
  addSavedAssembly: (assembly: SavedAssembly) => Promise<void> | void;
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
  alignObjects: (direction: 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom' | 'page-center-h' | 'page-center-v' | 'page-center-both') => void;
  distributeObjects: (direction: 'horizontal' | 'vertical') => void;
  equalSpaceObjects: (direction: 'horizontal' | 'vertical') => void;
  centerInPanel: (direction: 'horizontal' | 'vertical' | 'both') => void;
  matchObjectSize: (which: 'width' | 'height' | 'both') => void;
  updateSelected: (patch: Partial<CanvasSelection>) => void;
  reverseConnectorDirection: () => void;
  addVertexToSelected: () => void;
  deleteVertexFromSelected: () => void;
  convertSelectedConnector: (kind: 'line' | 'arrow' | 'polyline' | 'elbow') => void;
}
