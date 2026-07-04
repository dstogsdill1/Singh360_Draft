import { useState } from 'react';
import { renderPdfPage, uploadPdfForThumbnails, type PdfPageInfo } from '../api/client';

interface Props {
  projectId: string;
  onInsertImage: (url: string, name: string) => void;
  onCancel: () => void;
}

export default function PdfInsertModal({ projectId, onInsertImage, onCancel }: Props) {
  const [pages, setPages] = useState<PdfPageInfo[]>([]);
  const [pdfFile, setPdfFile] = useState('');
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(0);
  const [quality, setQuality] = useState<'high' | 'print'>('high');
  const [error, setError] = useState('');
  const [rendering, setRendering] = useState(false);

  const onFilePick = async (file: File) => {
    setError('');
    setLoading(true);
    try {
      const res = await uploadPdfForThumbnails(projectId, file);
      setPages(res.pages);
      setPdfFile(res.pdfFile);
      setSelected(0);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const doInsert = async () => {
    setError('');
    setRendering(true);
    try {
      const res = await renderPdfPage(projectId, { pdfFile, pageIndex: selected, quality });
      const meta = res.meta as { sourceFile?: string; pageIndex?: number };
      const label = `PDF_Page${(meta.pageIndex ?? selected) + 1}`;
      onInsertImage(res.asset.url, label);
    } catch (e) {
      setError(String(e));
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Insert PDF Page</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          {!pages.length ? (
            <div className="field">
              <label htmlFor="pdf-pick" title="Choose a PDF file to import">Choose a PDF</label>
              <label className="btn file-ribbon-btn" title="Upload a PDF and select a page to insert">
                {loading ? 'Loading…' : 'Select PDF…'}
                <input
                  id="pdf-pick"
                  type="file"
                  accept="application/pdf"
                  disabled={loading}
                  onChange={(e) => e.target.files?.[0] && void onFilePick(e.target.files[0])}
                />
              </label>
              <p className="renumber-note pdf-insert-hint">
                The selected PDF page will be rendered as a high-resolution PNG and
                inserted on the active drawing page. It stays crisp at 11×17 export.
              </p>
            </div>
          ) : (
            <>
              <div className="field">
                <label>Select a page to insert ({pages.length} pages)</label>
                <div className="pdf-page-grid">
                  {pages.map((pg) => (
                    <div
                      key={pg.page}
                      className={`pdf-page-card ${selected === pg.page ? 'active' : ''}`}
                      onClick={() => setSelected(pg.page)}
                    >
                      <img src={pg.thumbnailDataUrl} alt={`Page ${pg.page + 1}`} />
                      <div className="pdf-page-num">Page {pg.page + 1}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="field">
                <label htmlFor="pdf-quality" title="Higher quality renders sharper but takes a moment longer">Render Quality</label>
                <select
                  id="pdf-quality"
                  value={quality}
                  onChange={(e) => setQuality(e.target.value as 'high' | 'print')}
                >
                  <option value="high">High (200 DPI)</option>
                  <option value="print">Print / Crisp (300 DPI)</option>
                </select>
              </div>
            </>
          )}
          {error && <p className="lib-error">{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          {pages.length > 0 && (
            <button className="btn btn-primary" disabled={rendering} onClick={() => void doInsert()}>
              {rendering ? 'Rendering…' : `Insert Page ${selected + 1}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
