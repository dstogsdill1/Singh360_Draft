import { useRef, useState, type ChangeEvent, type MouseEvent } from 'react';
import { previewImportWorksheets, importWorksheets, type WorksheetPreview } from '../api/client';

type ImportMode = 'add' | 'replace';

interface Props {
  projectId: string;
  insertAfterPageId?: string;
  replacePageId?: string;
  replacePageTitle?: string;
  onImported: (pageIds: string[], renumberSuggested: boolean, replacedPageId?: string) => void;
  onCancel: () => void;
}

/** Add exactly one already-formatted worksheet without rebuilding the package. */
export default function ImportWorksheetModal({
  projectId,
  insertAfterPageId,
  replacePageId,
  replacePageTitle,
  onImported,
  onCancel,
}: Props) {
  const canReplace = Boolean(replacePageId);
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<WorksheetPreview[]>([]);
  const [selected, setSelected] = useState('');
  const [importMode, setImportMode] = useState<ImportMode>('add');
  const [preserveExact, setPreserveExact] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState<'pick' | 'preview'>('pick');
  const fileRef = useRef<HTMLInputElement>(null);

  const chooseFile = async (nextFile: File) => {
    setFile(nextFile);
    setError('');
    setLoading(true);
    try {
      const result = await previewImportWorksheets(projectId, nextFile);
      setSheets(result.sheets);
      setSelected(result.sheets[0]?.sheetName ?? '');
      setStep('preview');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const doImport = async () => {
    if (!file || !selected) return;
    setLoading(true);
    setError('');
    try {
      const result = await importWorksheets(projectId, file, [selected], {
        insertAfterPageId: importMode === 'add' ? insertAfterPageId : undefined,
        replacePageId: importMode === 'replace' ? replacePageId : undefined,
        preserveExact,
      });
      onImported(result.pageIds, result.renumberSuggested, result.replacedPageId);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const selectedSheet = sheets.find((sheet) => sheet.sheetName === selected);

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide" onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>Add One Worksheet from Excel</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          {step === 'pick' && (
            <div className="iw-pick">
              <p className="cw-note">
                Choose the workbook that already contains the finished sheet. Nothing else in the project is rebuilt.
              </p>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.xls"
                style={{ display: 'none' }}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  const picked = event.target.files?.[0];
                  event.currentTarget.value = '';
                  if (picked) void chooseFile(picked);
                }}
              />
              <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={loading}>
                {loading ? 'Reading workbook…' : 'Choose Workbook'}
              </button>
            </div>
          )}

          {step === 'preview' && (
            <div className="iw-preview">
              <p className="cw-note"><strong>{file?.name}</strong> — select the one worksheet to add.</p>

              <div className="iw-options" style={{ marginBottom: 12 }}>
                <label>Action</label>
                <div className="iw-mode-choice">
                  <label>
                    <input type="radio" name="singleSheetMode" checked={importMode === 'add'} onChange={() => setImportMode('add')} />
                    {' '}Add as one new page after the current page
                  </label>
                  {canReplace && (
                    <label style={{ marginLeft: 16 }}>
                      <input type="radio" name="singleSheetMode" checked={importMode === 'replace'} onChange={() => setImportMode('replace')} />
                      {' '}Replace current page source{replacePageTitle ? ` (${replacePageTitle})` : ''}
                    </label>
                  )}
                </div>
              </div>

              <table className="op-table">
                <thead>
                  <tr><th></th><th>Worksheet</th><th>Sheet Code</th><th>Page Title</th><th>Rows</th><th>Cols</th></tr>
                </thead>
                <tbody>
                  {sheets.map((sheet) => (
                    <tr key={sheet.sheetName} className={selected === sheet.sheetName ? 'current' : ''} onClick={() => setSelected(sheet.sheetName)}>
                      <td><input type="radio" name="singleWorksheet" checked={selected === sheet.sheetName} onChange={() => setSelected(sheet.sheetName)} /></td>
                      <td>{sheet.sheetName}</td>
                      <td>{sheet.sheetCode || 'NEW'}</td>
                      <td>{sheet.pageTitle || sheet.sheetName}</td>
                      <td>{sheet.rowEstimate ?? '?'}</td>
                      <td>{sheet.colEstimate ?? '?'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <label className="lib-showretired" style={{ marginTop: 12 }}>
                <input type="checkbox" checked={preserveExact} onChange={(event: ChangeEvent<HTMLInputElement>) => setPreserveExact(event.target.checked)} />
                {' '}Keep the Excel styling exactly and force it onto one Singh360 page
              </label>
              <p className="cw-note">
                {preserveExact
                  ? 'Uses the worksheet print area, merged cells, fills, borders, fonts, row heights, column widths, formulas, and embedded images. It will not auto-split into additional pages.'
                  : 'Uses the normal Singh360 page classifier and may normalize the worksheet.'}
              </p>

              {selectedSheet?.listedInIndex ? (
                <p className="cw-note">00_INDEX metadata found: <strong>{selectedSheet.sheetCode || 'NEW'}</strong> — {selectedSheet.pageTitle}</p>
              ) : (
                <p className="cw-note">This tab is not listed in 00_INDEX, so its sheet code will remain NEW until you renumber or edit it.</p>
              )}

              <button className="btn" onClick={() => fileRef.current?.click()} disabled={loading}>Choose Different Workbook</button>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.xls"
                style={{ display: 'none' }}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  const picked = event.target.files?.[0];
                  event.currentTarget.value = '';
                  if (picked) void chooseFile(picked);
                }}
              />
            </div>
          )}

          {error && <p className="lib-error" style={{ marginTop: 10 }}>{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={loading}>Cancel</button>
          {step === 'preview' && (
            <button className="btn btn-primary" onClick={() => void doImport()} disabled={loading || !selected}>
              {loading ? 'Adding sheet…' : importMode === 'replace' ? 'Replace Current Page Source' : 'Add Selected Sheet as One Page'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
