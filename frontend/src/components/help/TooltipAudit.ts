import { getTooltipDefinition, tooltipRegistry } from './tooltipRegistry';

export const TOOLTIP_TARGET_SELECTOR = [
  'button',
  '[role="button"]',
  '[role="tab"]',
  '[role="menuitem"]',
  'input',
  'select',
  'textarea',
  '[draggable="true"]',
  '[data-action]',
  '[data-status-chip]',
  '[data-page-pill]',
  '[data-resize-handle]',
].join(',');

export type TooltipAuditIssue = {
  helpId: string;
  tag: string;
  label: string;
};

export type TooltipAuditResult = {
  totalVisibleTargets: number;
  coveredTargets: number;
  missingHelpIds: TooltipAuditIssue[];
  invalidRegistryIds: TooltipAuditIssue[];
  duplicateIds: string[];
  inaccessibleControls: TooltipAuditIssue[];
};

const directText = (element: Element): string =>
  Array.from(element.childNodes)
    .filter((node) => node.nodeType === Node.TEXT_NODE)
    .map((node) => node.textContent || '')
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();

export function accessibleName(element: HTMLElement): string {
  const aria = element.getAttribute('aria-label')?.trim();
  if (aria) return aria;
  const labelledBy = element.getAttribute('aria-labelledby');
  if (labelledBy) {
    const value = labelledBy
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent?.trim() || '')
      .filter(Boolean)
      .join(' ');
    if (value) return value;
  }
  if (element instanceof HTMLInputElement && element.type !== 'hidden') {
    const label = element.labels?.[0]?.textContent?.trim();
    if (label) return label;
    if (element.placeholder) return element.placeholder;
    if (element.value && ['button', 'submit', 'reset'].includes(element.type)) return element.value;
  }
  if (element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
    const label = element.labels?.[0]?.textContent?.trim();
    if (label) return label;
  }
  return directText(element) || element.textContent?.replace(/\s+/g, ' ').trim() || '';
}

const helpRules: Array<[RegExp, string]> = [
  [/save\s*\+\s*write excel|writing excel/i, 'save.writeExcel'],
  [/save data workspace|save workspace edits/i, 'workspace.save'],
  [/save now|save project/i, 'save.localProject'],
  [/what is unsaved/i, 'status.whatUnsaved'],
  [/project home/i, 'nav.projectHome'],
  [/data workspace/i, 'workspace.open'],
  [/project files/i, 'project.openFolder'],
  [/page editor/i, 'view.canvas'],
  [/visual page manager|review drawing pages/i, 'pageManager.open'],
  [/component library|component builder/i, 'nav.componentLibrary'],
  [/symbol mapper/i, 'nav.symbolMapper'],
  [/help|instructions/i, 'nav.help'],
  [/create (new|a different) project/i, 'project.new'],
  [/open project/i, 'project.open'],
  [/upload workbook|import workbook/i, 'project.importWorkbook'],
  [/change workbook|choose correct workbook|browse/i, 'project.relinkWorkbook'],
  [/confirm link|link workbook/i, 'project.linkWorkbook'],
  [/open workbook|open in excel/i, 'project.refreshWorkbook'],
  [/backups|back up/i, 'project.backup'],
  [/delete this project|remove project|archive project/i, 'project.delete'],
  [/export pdf|drawing set/i, 'export.pdf'],
  [/export (project )?package/i, 'export.projectPackage'],
  [/export worksheet|export source/i, 'export.worksheet'],
  [/previous/i, 'pages.previous'],
  [/next/i, 'pages.next'],
  [/rename/i, 'pages.rename'],
  [/duplicate page/i, 'pages.duplicate'],
  [/delete page/i, 'pages.delete'],
  [/include|publish this page/i, 'pages.include'],
  [/exclude|keep as source/i, 'pages.exclude'],
  [/fit width/i, 'view.fitWidth'],
  [/fit page/i, 'view.fitPage'],
  [/actual size|100%/i, 'view.zoom100'],
  [/zoom in/i, 'view.zoomIn'],
  [/zoom out/i, 'view.zoomOut'],
  [/normalized/i, 'view.normalized'],
  [/source view|source$/i, 'view.source'],
  [/excel layout/i, 'view.excelLayout'],
  [/undo/i, 'edit.undo'],
  [/redo/i, 'edit.redo'],
  [/cut/i, 'edit.cut'],
  [/copy/i, 'edit.copy'],
  [/paste/i, 'edit.paste'],
  [/duplicate/i, 'edit.duplicate'],
  [/delete|remove/i, 'edit.delete'],
  [/insert text|^text$/i, 'insert.text'],
  [/add table|insert table/i, 'insert.table'],
  [/image/i, 'insert.image'],
  [/pdf.*crop|crop.*pdf/i, 'insert.pdfCrop'],
  [/symbol legend|legend builder/i, 'insert.symbolLegend'],
  [/connector|line|arrow|polyline|elbow/i, 'insert.connector'],
  [/callout/i, 'insert.callout'],
  [/bring to front/i, 'arrange.front'],
  [/bring forward/i, 'arrange.forward'],
  [/send backward/i, 'arrange.backward'],
  [/send to back/i, 'arrange.back'],
  [/align left/i, 'arrange.alignLeft'],
  [/align center/i, 'arrange.alignCenter'],
  [/align right/i, 'arrange.alignRight'],
  [/align top/i, 'arrange.alignTop'],
  [/align middle/i, 'arrange.alignMiddle'],
  [/align bottom/i, 'arrange.alignBottom'],
  [/distribute horizontal/i, 'arrange.distributeHorizontal'],
  [/distribute vertical/i, 'arrange.distributeVertical'],
  [/snap/i, 'arrange.snap'],
  [/group/i, 'object.group'],
  [/ungroup/i, 'object.ungroup'],
  [/opacity/i, 'object.opacity'],
  [/rotation/i, 'object.rotation'],
  [/border color/i, 'object.borderColor'],
  [/border width/i, 'object.borderWidth'],
  [/border/i, 'object.border'],
  [/shadow/i, 'object.shadow'],
  [/direct insert|insert component/i, 'library.directInsert'],
  [/favorite/i, 'library.favorite'],
  [/search/i, 'library.search'],
  [/save legend/i, 'library.saveLegend'],
  [/scan.*symbol/i, 'symbolMapper.scan'],
  [/apply highlight/i, 'symbolMapper.apply'],
  [/auto-detect tables/i, 'excelLayout.addTable'],
  [/add table region/i, 'excelLayout.addTable'],
  [/remove table region/i, 'edit.delete'],
  [/preview drawing layout/i, 'excelLayout.pageBoundary'],
  [/update drawings/i, 'save.workspace'],
  [/close preview/i, 'dialog.close'],
  [/restore/i, 'recovery.restore'],
  [/cancel/i, 'dialog.cancel'],
  [/confirm|apply|ok|yes/i, 'dialog.confirm'],
];

function statusHelpId(label: string): string | undefined {
  if (/unsaved workspace/i.test(label)) return 'status.unsavedWorkspace';
  if (/unsaved project|unsaved changes/i.test(label)) return 'status.unsavedProject';
  if (/sync pending|workbook update pending/i.test(label)) return 'status.syncPending';
  if (/conflict|both.*changed/i.test(label)) return 'status.conflict';
  if (/save failed/i.test(label)) return 'save.retry';
  if (/saved|ready|clean|match/i.test(label)) return 'status.localSaved';
  return undefined;
}

export function inferHelpId(element: HTMLElement): string {
  const existing = element.dataset.helpId;
  if (existing && getTooltipDefinition(existing)) return existing;
  const label = [
    accessibleName(element),
    element.getAttribute('title') || '',
    element.getAttribute('placeholder') || '',
    element.getAttribute('name') || '',
    element.id,
  ].join(' ').replace(/\s+/g, ' ').trim();

  if (element.matches('[data-status-chip], .status-pill, .workspace-status, .sync-badge')) {
    return statusHelpId(label) || 'control.status';
  }
  if (element.closest('.univer-host')) return 'workspace.cell';
  if (element.closest('.excel-layout-canvas')) return 'excelLayout.table';
  if (element.matches('[data-resize-handle]')) return 'control.drag';
  if (element.matches('[draggable="true"]')) {
    return element.closest('.page-manager, .page-manager-modal') ? 'pageManager.drag' : 'pages.dragReorder';
  }
  if (element.matches('[role="tab"], .ribbon-tab')) return 'control.tab';
  for (const [pattern, helpId] of helpRules) {
    if (pattern.test(label)) return helpId;
  }
  if (element instanceof HTMLInputElement) {
    if (['checkbox', 'radio', 'color', 'range'].includes(element.type)) return 'control.toggle';
    return 'control.input';
  }
  if (element instanceof HTMLSelectElement) return 'control.select';
  if (element instanceof HTMLTextAreaElement) return 'control.input';
  return 'control.action';
}

export function hydrateTooltipTargets(root: ParentNode = document): void {
  const targets = [
    ...(root instanceof HTMLElement && root.matches(TOOLTIP_TARGET_SELECTOR) ? [root] : []),
    ...root.querySelectorAll<HTMLElement>(TOOLTIP_TARGET_SELECTOR),
  ];
  targets.forEach((element) => {
    if (element.matches('input[type="hidden"]')) return;
    const originalTitle = element.getAttribute('title')?.trim();
    const helpId = inferHelpId(element);
    element.dataset.helpId = helpId;
    if (originalTitle) {
      element.dataset.originalTitle = originalTitle;
      element.removeAttribute('title');
    }
    if (!accessibleName(element)) {
      const definition = getTooltipDefinition(helpId);
      if (definition) element.setAttribute('aria-label', definition.title);
    }
    if (
      element.getAttribute('role') === 'button'
      && !element.hasAttribute('tabindex')
      && !element.matches('button, input, select, textarea')
    ) {
      element.tabIndex = 0;
    }
  });
}

export function isVisible(element: HTMLElement): boolean {
  if (element.hidden || element.getAttribute('aria-hidden') === 'true') return false;
  const style = window.getComputedStyle(element);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

export function runTooltipAudit(root: ParentNode = document): TooltipAuditResult {
  hydrateTooltipTargets(root);
  const targets = Array.from(root.querySelectorAll<HTMLElement>(TOOLTIP_TARGET_SELECTOR))
    .filter((element) => !element.matches('input[type="hidden"]') && isVisible(element));
  const missingHelpIds: TooltipAuditIssue[] = [];
  const invalidRegistryIds: TooltipAuditIssue[] = [];
  const inaccessibleControls: TooltipAuditIssue[] = [];
  const uniqueHelpIds = new Map<string, number>();
  let coveredTargets = 0;

  targets.forEach((element) => {
    const issue = {
      helpId: element.dataset.helpId || '',
      tag: element.tagName.toLowerCase(),
      label: accessibleName(element),
    };
    if (!issue.helpId) missingHelpIds.push(issue);
    else if (!getTooltipDefinition(issue.helpId)) invalidRegistryIds.push(issue);
    else coveredTargets += 1;
    if (!issue.label) inaccessibleControls.push(issue);
    if (element.dataset.helpUnique === 'true' && issue.helpId) {
      uniqueHelpIds.set(issue.helpId, (uniqueHelpIds.get(issue.helpId) || 0) + 1);
    }
  });

  return {
    totalVisibleTargets: targets.length,
    coveredTargets,
    missingHelpIds,
    invalidRegistryIds,
    duplicateIds: [...uniqueHelpIds.entries()].filter(([, count]) => count > 1).map(([helpId]) => helpId),
    inaccessibleControls,
  };
}

export function validateTooltipRegistry(): string[] {
  return Object.entries(tooltipRegistry).flatMap(([helpId, definition]) => {
    const errors: string[] = [];
    if (!helpId.trim()) errors.push('Registry contains an empty help ID.');
    if (!definition.title.trim()) errors.push(`${helpId}: title is empty.`);
    if (!definition.body.trim()) errors.push(`${helpId}: body is empty.`);
    return errors;
  });
}

declare global {
  interface Window {
    __S360_TOOLTIP_AUDIT__?: () => TooltipAuditResult;
  }
}
