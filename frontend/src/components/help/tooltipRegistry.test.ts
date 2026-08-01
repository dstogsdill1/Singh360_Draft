import { SAVE_STATE_LABELS } from '../../model/saveState';
import { validateTooltipRegistry } from './TooltipAudit';
import { tooltipRegistry } from './tooltipRegistry';

const requiredHelpIds = [
  'project.new',
  'project.open',
  'nav.projectHome',
  'nav.pageManager',
  'nav.componentLibrary',
  'nav.symbolMapper',
  'status.unsavedProject',
  'status.unsavedWorkspace',
  'status.syncPending',
  'status.conflict',
  'status.whatUnsaved',
  'save.localProject',
  'save.workspace',
  'export.pdf',
  'pages.dragReorder',
  'view.excelLayout',
  'edit.undo',
  'insert.pdfCrop',
  'object.select',
  'workspace.cell',
  'workspace.protectedCell',
  'excelLayout.table',
  'pageManager.drag',
  'pdfCrop.apply',
  'library.directInsert',
  'symbolMapper.apply',
  'recovery.restore',
  'warning.disabled',
] as const;

export function runTooltipRegistryContractTests(): void {
  const errors = validateTooltipRegistry();
  if (errors.length) throw new Error(errors.join('\n'));
  requiredHelpIds.forEach((helpId) => {
    if (!tooltipRegistry[helpId]) throw new Error(`Missing required tooltip ${helpId}`);
  });
  if (tooltipRegistry['save.localProject'].saveScope !== 'local-project') {
    throw new Error('Local save tooltip has the wrong save scope.');
  }
  if (tooltipRegistry['export.pdf'].saveScope !== 'export-only') {
    throw new Error('PDF tooltip has the wrong save scope.');
  }
  if (new Set(Object.keys(tooltipRegistry)).size !== Object.keys(tooltipRegistry).length) {
    throw new Error('Tooltip registry keys must be unique.');
  }
  if (SAVE_STATE_LABELS.dirtyWorkspace !== 'UNSAVED WORKSPACE EDITS') {
    throw new Error('Workspace dirty label drifted from the specification.');
  }
  if (SAVE_STATE_LABELS.cleanLocal !== 'PROJECT SAVED') {
    throw new Error('Standalone saved label drifted from the specification.');
  }
}

runTooltipRegistryContractTests();
