export type PageType = 'data-grid' | 'canvas' | 'underlay' | 'hybrid' | 'cover' | 'index';

export type BlockType =
  | 'title'
  | 'subtitle'
  | 'paragraph'
  | 'bulletList'
  | 'sectionHeading'
  | 'table'
  | 'matrix'
  | 'imagePlaceholder'
  | 'canvas'
  | 'note'
  | 'cover'
  | 'underlayPlaceholder';

export interface PageBlock {
  id: string;
  type: BlockType;
  sourceWorksheetId?: string;
  sourceRange?: string;
  text?: string;
  items?: string[];
  headers?: string[];
  rows?: string[][];
  filename?: string;
  styleRole?: string;
  editable?: boolean;
  url?: string;
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
  styles?: Record<string, CellStyle>;
  mergedCells?: MergedCell[];
  rowHeights?: Record<string, number>;
  columnWidths?: Record<string, number>;
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
  template?: string;
  templateId: string;
  linkedWorksheetId?: string;
  blocks?: PageBlock[];
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
    location?: string;
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

export interface CanvasApi {
  addText: () => void;
  addRect: () => void;
  addCircle: () => void;
  addLine: () => void;
  addArrow: () => void;
  addPolyline: () => void;
  addElbow: () => void;
  setLineStyle: (style: LineStyle) => void;
  startBus: (opts: BusOptions) => void;
  addImage: (url: string, name?: string, at?: { clientX: number; clientY: number }) => void;
  addPdfCrop: (url: string, name: string, opts?: { underlay?: boolean; meta?: PdfCropInsertMeta }) => void;
  addComponent: (url: string, name: string, label: string | null, at?: { clientX: number; clientY: number }) => void;
  addComponentPair: (sourceUrl: string, symbolUrl: string, name: string, label: string | null, at?: { clientX: number; clientY: number }) => void;
  addLegend: (presetIds?: string[]) => void;
  addPageTitle: (text: string) => void;
  addSectionHeader: (text: string) => void;
  addNote: (text: string) => void;
  deleteSelected: () => void;
  duplicateSelected: () => void;
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
