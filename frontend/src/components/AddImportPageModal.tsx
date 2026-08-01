import { useEffect, useMemo, useState } from 'react';
import {
  commitPdfDrawingImport,
  previewPdfDrawing,
  Singh360ApiError,
  type PdfDrawingPreview,
  type PdfDrawingImportProgress,
} from '../api/client';
import type { ProjectModel } from '../model/types';
import { waitForBrowserPaint } from '../model/browserPaint';
import { pdfImportRequestSelection } from '../model/pdfImportSelection';
import { nextLogicalSheetCode } from '../model/sheetCodes';

type Choice = 'blank' | 'pdf' | 'image' | 'table' | 'text' | 'template';
type ExistingPdfGroup = PdfDrawingPreview['existingGroups'][number];
type ModalProgress = PdfDrawingImportProgress | {
  phase: 'upload' | 'csv';
  completed: number;
  total: number;
  message: string;
};

const PROGRESS_PHASE_LABELS: Record<ModalProgress['phase'], string> = {
  upload: 'Upload and preview',
  csv: 'CSV import',
  validate: 'Validate',
  render: 'Render pages',
  install: 'Install project-local assets',
  compose: 'Create drawing pages',
  save: 'Save and verify project',
  complete: 'Complete',
};

export function buildPdfReplacementMapping(
  preview: PdfDrawingPreview,
  group: ExistingPdfGroup,
  selectedPageIndices: number[],
): Array<{ existingPageId: string; pageIndex: number }> {
  const count = group.pageIds.length;
  if (!count) throw new Error('The selected existing PDF import contains no replaceable pages.');
  if (group.pageIndices.length !== count || group.pageFingerprints.length !== count) {
    throw new Error(`The existing PDF import metadata is incomplete for ${group.originalName}; choose Add as New Pages or repair the import history.`);
  }
  if (new Set(group.pageIds).size !== count || group.pageIds.some((pageId) => !pageId)) {
    throw new Error(`The existing PDF import has duplicate or missing stable page IDs for ${group.originalName}.`);
  }

  const selected = [...new Set(selectedPageIndices)].sort((a, b) => a - b);
  const previewByIndex = new Map(preview.pages.map((page) => [page.pageIndex, page]));
  if (selected.some((pageIndex) => !previewByIndex.has(pageIndex))) {
    throw new Error('The revised PDF selection contains a page that is no longer available; upload it again.');
  }
  const available = new Set(selected);
  const assigned = new Map<number, number>();
  const assign = (position: number, pageIndex: number) => {
    assigned.set(position, pageIndex);
    available.delete(pageIndex);
  };

  // Pass 1: unchanged pages remain identifiable even if the revised PDF was
  // reordered. Prefer the prior source index when duplicate visual pages share
  // one fingerprint, then use the lowest revised index for determinism.
  group.pageFingerprints.forEach((fingerprint, position) => {
    if (!fingerprint || assigned.has(position)) return;
    const candidates = [...available].filter(
      (pageIndex) => previewByIndex.get(pageIndex)?.fingerprint === fingerprint,
    );
    if (!candidates.length) return;
    const priorIndex = group.pageIndices[position];
    assign(position, candidates.includes(priorIndex) ? priorIndex : candidates[0]);
  });

  // Pass 2: revised content normally keeps its original PDF page index.
  group.pageIndices.forEach((priorIndex, position) => {
    if (!assigned.has(position) && available.has(priorIndex)) assign(position, priorIndex);
  });

  // Pass 3: pair the remaining pages in stable existing-project/source order.
  const remainingPages = [...available].sort((a, b) => a - b);
  const remainingPositions = group.pageIds
    .map((_, position) => position)
    .filter((position) => !assigned.has(position));
  const remainingCount = Math.min(remainingPages.length, remainingPositions.length);
  remainingPositions.slice(0, remainingCount).forEach((position, index) => assign(position, remainingPages[index]));

  const mapping = group.pageIds.flatMap((existingPageId, position) => {
    const pageIndex = assigned.get(position);
    return pageIndex === undefined ? [] : [{ existingPageId, pageIndex }];
  });
  if (!mapping.length) {
    throw new Error(`No revised PDF pages could be mapped to ${group.originalName}.`);
  }
  if (new Set(mapping.map((item) => item.pageIndex)).size !== mapping.length) {
    throw new Error(`The revised PDF mapping is ambiguous for ${group.originalName}; no pages were changed.`);
  }
  return mapping;
}

interface Props {
  project: ProjectModel;
  onClose: () => void;
  onProjectImported: (project: ProjectModel, pageIds: string[]) => Promise<boolean>;
  onBlank: (title: string, code: string) => void;
  onText: (title: string, code: string) => void;
  onImage: (file: File) => Promise<boolean>;
  onTable: () => void;
  onCsv: (file: File) => Promise<boolean>;
  onTemplate: () => void;
}

function exactMessage(error: unknown): string {
  if (error instanceof Singh360ApiError) {
    const phase = typeof error.payload.phase === 'string' ? error.payload.phase : '';
    const code = typeof error.payload.code === 'string' ? error.payload.code : '';
    const pageIndex = typeof error.payload.pageIndex === 'number' ? error.payload.pageIndex : null;
    const context = [
      phase ? `Phase: ${phase}` : '',
      pageIndex !== null ? `PDF page: ${pageIndex + 1}` : '',
      code ? `Error code: ${code}` : '',
    ].filter(Boolean).join(' · ');
    return context ? `${error.message}\n${context}` : error.message;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}

export default function AddImportPageModal({
  project,
  onClose,
  onProjectImported,
  onBlank,
  onText,
  onImage,
  onTable,
  onCsv,
  onTemplate,
}: Props) {
  const [choice, setChoice] = useState<Choice>('blank');
  const [title, setTitle] = useState('New Drawing Page');
  const [code, setCode] = useState(() => nextLogicalSheetCode(project.pages));
  const [preview, setPreview] = useState<PdfDrawingPreview | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [placementMode, setPlacementMode] = useState<'full_sheet' | 'fit_body'>('full_sheet');
  const [action, setAction] = useState<'add' | 'replace'>('add');
  const [replaceGroupId, setReplaceGroupId] = useState('');
  const [progress, setProgress] = useState<ModalProgress | null>(null);
  const [error, setError] = useState('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState('');
  const [pdfCommitted, setPdfCommitted] = useState(false);
  const busy = progress !== null;

  const showProgressAfterPaint = async (next: ModalProgress) => {
    setProgress(next);
    await waitForBrowserPaint();
  };

  const selectedPages = useMemo(() => [...selected].sort((a, b) => a - b), [selected]);
  const replacementGroup = preview?.existingGroups.find((group) => group.groupId === replaceGroupId);
  const replacementPlan = useMemo(() => {
    if (action !== 'replace' || !preview || !replacementGroup) return { mapping: undefined, error: '', notice: '' };
    try {
      const mapping = buildPdfReplacementMapping(preview, replacementGroup, selectedPages);
      const mappedExisting = new Set(mapping.map((item) => item.existingPageId));
      const mappedRevised = new Set(mapping.map((item) => item.pageIndex));
      const unmatchedExisting = replacementGroup.pageIds.length - mappedExisting.size;
      const unmatchedRevised = selectedPages.filter((pageIndex) => !mappedRevised.has(pageIndex));
      const details = [
        `${mapping.length} revised page${mapping.length === 1 ? '' : 's'} will replace ${mapping.length} existing page${mapping.length === 1 ? '' : 's'} in place.`,
        unmatchedExisting
          ? `${unmatchedExisting} unmatched existing page${unmatchedExisting === 1 ? '' : 's'} will remain unchanged.`
          : '',
        unmatchedRevised.length
          ? `${unmatchedRevised.length} selected revised page${unmatchedRevised.length === 1 ? '' : 's'} (${unmatchedRevised.map((pageIndex) => pageIndex + 1).join(', ')}) will not be imported; choose Add as New Pages to keep them.`
          : '',
      ].filter(Boolean);
      return { mapping, error: '', notice: details.join(' ') };
    } catch (nextError) {
      return { mapping: undefined, error: exactMessage(nextError), notice: '' };
    }
  }, [action, preview, replacementGroup, selectedPages]);

  const importImage = async (file: File) => {
    setError('');
    setProgress({
      phase: 'upload',
      completed: 0,
      total: 1,
      message: `Copying ${file.name} into this project and creating its drawing page`,
    });
    try {
      const imported = await onImage(file);
      if (!imported) throw new Error('Image import did not complete. The existing project pages were not replaced.');
    } catch (nextError) {
      setError(exactMessage(nextError));
    } finally {
      setProgress(null);
    }
  };

  useEffect(() => {
    if (choice !== 'image' || busy) return undefined;
    const paste = (event: ClipboardEvent) => {
      const item = [...(event.clipboardData?.items || [])].find((candidate) => candidate.type.startsWith('image/'));
      const pasted = item?.getAsFile();
      if (!pasted) return;
      event.preventDefault();
      const extension = pasted.type.split('/')[1]?.replace('jpeg', 'jpg') || 'png';
      void importImage(new File([pasted], `Pasted Image.${extension}`, { type: pasted.type }));
    };
    document.addEventListener('paste', paste);
    return () => document.removeEventListener('paste', paste);
  }, [busy, choice, onImage]);

  const uploadPdf = async (file: File) => {
    setError('');
    setProgress({
      phase: 'upload',
      completed: 0,
      total: 0,
      message: 'Uploading the PDF and preparing selectable page previews',
    });
    try {
      const next = await previewPdfDrawing(project.id, file);
      setPreview(next);
      setSelected(new Set(next.pages.map((page) => page.pageIndex)));
      const group = next.existingGroups.find((item) => item.sameName) ?? next.existingGroups[0];
      setReplaceGroupId(group?.groupId || '');
      setAction(group?.sameName ? 'replace' : 'add');
    } catch (nextError) {
      setError(exactMessage(nextError));
    } finally {
      setProgress(null);
    }
  };

  const commitPdf = async () => {
    if (!preview || !selectedPages.length) {
      setError('Select at least one PDF page.');
      return;
    }
    if (action === 'replace' && !replacementGroup) {
      setError('Choose the existing PDF import to replace.');
      return;
    }
    if (action === 'replace' && replacementPlan.error) {
      setError(replacementPlan.error);
      return;
    }
    const mapping = action === 'replace' ? replacementPlan.mapping : undefined;
    const requestPages = pdfImportRequestSelection(action, selectedPages, mapping);
    setError('');
    setProgress({
      phase: 'validate',
      completed: 0,
      total: requestPages.length,
      message: 'Validating the staged PDF import',
    });
    let closeAfterComplete = false;
    try {
      const result = await commitPdfDrawingImport(project.id, {
        previewId: preview.previewId,
        selectedPages: requestPages,
        placementMode,
        action,
        replaceGroupId: replacementGroup?.groupId,
        mapping,
        titlePrefix: title.trim() || undefined,
        firstSheetCode: code.trim() || undefined,
      }, setProgress);
      setPdfCommitted(true);
      await showProgressAfterPaint({
        phase: 'save',
        completed: requestPages.length,
        total: requestPages.length,
        message: 'Reconciling the imported pages with the latest editor state and confirming the save',
      });
      const saved = await onProjectImported(
        result.project,
        result.pageIds.length ? result.pageIds : result.replacedPageIds,
      );
      if (!saved) throw new Error('The imported PDF pages could not be reconciled with the latest editor state. The import remains recoverable in project history.');
      await showProgressAfterPaint({
        phase: 'complete',
        completed: requestPages.length,
        total: requestPages.length,
        message: `Imported and verified ${requestPages.length} project-local PDF page${requestPages.length === 1 ? '' : 's'}`,
      });
      closeAfterComplete = true;
      onClose();
    } catch (nextError) {
      setError(exactMessage(nextError));
    } finally {
      if (!closeAfterComplete) setProgress(null);
    }
  };

  const importCsv = async (file: File) => {
    setError('');
    setProgress({
      phase: 'csv',
      completed: 0,
      total: 0,
      message: `Importing ${file.name} as project-local table data`,
    });
    try {
      const imported = await onCsv(file);
      if (imported) onClose();
      else setError('CSV import failed. The project was not changed.');
    } catch (nextError) {
      setError(exactMessage(nextError));
    } finally {
      setProgress(null);
    }
  };

  const previewCsv = async (file: File) => {
    setError('');
    setCsvFile(file);
    try {
      const source = await file.text();
      const lines = source.replace(/^\uFEFF/, '').split(/\r?\n/);
      setCsvPreview(lines.slice(0, 12).join('\n'));
    } catch (nextError) {
      setCsvFile(null);
      setCsvPreview('');
      setError(`CSV preview failed. ${exactMessage(nextError)}`);
    }
  };

  const choices: Array<[Choice, string, string]> = [
    ['blank', 'Blank Layout Page', 'Empty ANSI B canvas with the standard title block.'],
    ['pdf', 'Finished PDF Drawing', 'Import one, selected, or all PDF pages into the project.'],
    ['image', 'Image / Screenshot', 'PNG, JPG, SVG, or WebP contained without cropping.'],
    ['table', 'Excel Worksheet / CSV Table', 'One-time editable import; never writes back.'],
    ['text', 'Text / Table Page', 'Notes, scope, bill of material, schedule, or matrix.'],
    ['template', 'Page Template', 'Create from an approved reusable page template.'],
  ];

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal add-import-modal" role="dialog" aria-modal="true" aria-labelledby="add-import-title" aria-busy={busy}>
        <div className="modal-head">
          <div><h2 id="add-import-title">Add / Import Page</h2><p>Every created page is stored inside this Singh360 project.</p></div>
          <button type="button" className="modal-x" aria-label="Close Add or Import Page" onClick={onClose} disabled={busy}>×</button>
        </div>
        <div className="modal-body add-import-layout">
          <nav className="add-import-choices" aria-label="Page type">
            {choices.map(([value, label, hint]) => (
              <button key={value} type="button" disabled={busy || pdfCommitted} className={choice === value ? 'active' : ''} onClick={() => setChoice(value)}>
                <b>{label}</b><span>{hint}</span>
              </button>
            ))}
          </nav>
          <div className="add-import-workspace">
            {(choice === 'blank' || choice === 'text') && (
              <>
                <label>Page Title<input value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} /></label>
                <label>Sheet Code<input value={code} disabled={busy} onChange={(event) => setCode(event.target.value)} /></label>
                <button type="button" className="primary" disabled={busy} onClick={() => choice === 'blank' ? onBlank(title, code) : onText(title, code)}>
                  Create {choice === 'blank' ? 'Blank Layout' : 'Text / Table'} Page
                </button>
              </>
            )}
            {choice === 'image' && (
              <div
                className="file-drop-control"
                onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }}
                onDrop={(event) => {
                  event.preventDefault();
                  if (busy) return;
                  const file = [...event.dataTransfer.files].find((candidate) => candidate.type.startsWith('image/'));
                  if (file) void importImage(file);
                }}
              >
                <b>Drop or paste an image here</b>
                <span>Images are contained inside the drawing body without cropping.</span>
                <label>Choose Image
                  <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" disabled={busy} onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void importImage(file);
                  }} />
                </label>
              </div>
            )}
            {choice === 'table' && (
              <div className="table-import-choices">
                <p>Choose a one-time import. The copied table stays in this project and is never written back.</p>
                <button type="button" className="primary" disabled={busy} onClick={onTable}>Choose Excel Worksheet</button>
                <label className="file-drop-control">Choose CSV
                  <input type="file" accept="text/csv,.csv" disabled={busy} onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void previewCsv(file);
                  }} />
                </label>
                {csvFile ? (
                  <div className="csv-import-preview">
                    <p><b>{csvFile.name}</b> · {csvFile.size.toLocaleString()} bytes</p>
                    <pre aria-label="CSV source preview">{csvPreview || '(empty CSV)'}</pre>
                    <button type="button" className="primary" disabled={busy} onClick={() => void importCsv(csvFile)}>Import CSV Table</button>
                  </div>
                ) : null}
              </div>
            )}
            {choice === 'template' && <button type="button" className="primary" disabled={busy} onClick={onTemplate}>Open Page Templates</button>}
            {choice === 'pdf' && (
              <div className="pdf-drawing-import">
                <label className="file-drop-control">Choose PDF
                  <input type="file" accept="application/pdf,.pdf" disabled={busy || pdfCommitted} onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void uploadPdf(file);
                  }} />
                </label>
                {preview ? (
                  <>
                    <div className="pdf-import-options">
                      <span><b>{preview.originalName}</b> · {preview.pageCount} pages</span>
                      <button type="button" disabled={busy || pdfCommitted} onClick={() => setSelected(new Set(preview.pages.map((page) => page.pageIndex)))}>Select All</button>
                      <button type="button" disabled={busy || pdfCommitted} onClick={() => setSelected(new Set())}>Select None</button>
                      <label>Placement
                        <select value={placementMode} disabled={busy || pdfCommitted} onChange={(event) => setPlacementMode(event.target.value as 'full_sheet' | 'fit_body')}>
                          <option value="full_sheet">Full Sheet Already Formatted</option>
                          <option value="fit_body">Fit Inside Singh360 Drawing Body</option>
                        </select>
                      </label>
                    </div>
                    {preview.existingGroups.length > 0 ? (
                      <fieldset className="pdf-reimport-choice">
                        <legend>Revised PDF behavior</legend>
                        <label><input type="radio" disabled={busy || pdfCommitted} checked={action === 'replace'} onChange={() => setAction('replace')} /> Replace Existing Pages</label>
                        <label><input type="radio" disabled={busy || pdfCommitted} checked={action === 'add'} onChange={() => setAction('add')} /> Add as New Pages</label>
                        {action === 'replace' ? (
                          <select aria-label="Existing PDF import" value={replaceGroupId} disabled={busy || pdfCommitted} onChange={(event) => setReplaceGroupId(event.target.value)}>
                            {preview.existingGroups.map((group) => <option key={group.groupId} value={group.groupId}>{group.originalName} · {group.pageIds.length} pages · revision {group.revision}{group.sameName ? ' · same filename' : ''}</option>)}
                          </select>
                        ) : null}
                      </fieldset>
                    ) : null}
                    {replacementPlan.error ? <p className="import-error">{replacementPlan.error}</p> : null}
                    {replacementPlan.notice ? <p role="status" className="import-warning">{replacementPlan.notice}</p> : null}
                    <div className="pdf-page-grid">
                      {preview.pages.map((page) => (
                        <label key={page.pageIndex} className={selected.has(page.pageIndex) ? 'selected' : ''}>
                          <input type="checkbox" disabled={busy || pdfCommitted} checked={selected.has(page.pageIndex)} onChange={() => setSelected((current) => {
                            const next = new Set(current);
                            if (next.has(page.pageIndex)) next.delete(page.pageIndex); else next.add(page.pageIndex);
                            return next;
                          })} />
                          <img src={page.thumbnail} alt={`PDF page ${page.pageNumber}`} />
                          <span>Page {page.pageNumber}</span>
                        </label>
                      ))}
                    </div>
                    <button type="button" className="primary" disabled={busy || pdfCommitted || !selectedPages.length || !!replacementPlan.error} onClick={() => void commitPdf()}>
                      {action === 'replace' ? 'Replace Existing Pages' : 'Import Selected Pages'}
                    </button>
                  </>
                ) : null}
              </div>
            )}
            {progress ? (
              <div
                role="status"
                aria-live="polite"
                aria-atomic="true"
                className="import-progress"
                data-phase={progress.phase}
              >
                <div>
                  <b>{PROGRESS_PHASE_LABELS[progress.phase]}</b>
                  <span>{progress.message}</span>
                </div>
                {progress.total > 0 ? (
                  <>
                    <progress max={progress.total} value={progress.completed} aria-label="PDF import page progress" />
                    <output>{progress.completed} of {progress.total} pages</output>
                  </>
                ) : null}
              </div>
            ) : null}
            {error ? <pre role="alert" className="import-error">{error}</pre> : null}
          </div>
        </div>
        <div className="modal-foot"><button type="button" onClick={onClose} disabled={busy}>Close</button></div>
      </section>
    </div>
  );
}
