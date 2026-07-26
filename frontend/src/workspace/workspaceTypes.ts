import type { WorkbookDocument } from '../api/client';

export type WorkspaceDocument = WorkbookDocument;
export type WorkspaceStatus = 'loading' | 'saved' | 'dirty' | 'saving' | 'conflict' | 'error';
