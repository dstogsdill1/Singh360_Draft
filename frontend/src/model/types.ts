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
  };
  worksheets: Worksheet[];
  pages: PageModel[];
  sources: Record<string, unknown>[];
  modified?: string;
  projectFolder?: string;
  projectDisplayName?: string;
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
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  angle?: number;
  locked: boolean;
}

export interface CanvasApi {
  addText: () => void;
  addRect: () => void;
  addCircle: () => void;
  addLine: () => void;
  addArrow: () => void;
  addImage: (url: string, name?: string) => void;
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
  updateSelected: (patch: Partial<CanvasSelection>) => void;
}
