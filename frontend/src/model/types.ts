export type PageType = 'data-grid' | 'canvas' | 'underlay' | 'hybrid' | 'cover' | 'index';

export interface Worksheet {
  id: string;
  name: string;
  grid: string[][];
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
  };
  worksheets: Worksheet[];
  pages: PageModel[];
  sources: Record<string, unknown>[];
  modified?: string;
}
