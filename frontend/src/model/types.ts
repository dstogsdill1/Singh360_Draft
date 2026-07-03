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
  sheetTitle: string;
  sheetTab: string;
  pageType: PageType;
  templateId: string;
  linkedWorksheetId?: string;
  blocks?: PageBlock[];
  canvasObjects: Record<string, unknown>[];
  notes: string;
  pageNumber?: number | null;
  pageTotal?: number;
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
}

export type ViewMode = 'normalized' | 'source';

export interface CanvasSelection {
  type: string;
  fill: string;
  stroke: string;
  strokeWidth: number;
  fontSize?: number;
  locked: boolean;
}

export interface CanvasApi {
  addText: () => void;
  addRect: () => void;
  addLine: () => void;
  addArrow: () => void;
  deleteSelected: () => void;
  duplicateSelected: () => void;
  undo: () => void;
  redo: () => void;
  updateSelected: (patch: Partial<CanvasSelection>) => void;
}
