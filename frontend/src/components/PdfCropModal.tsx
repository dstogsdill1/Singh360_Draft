// S360 PDF CROP IMAGE BOUNDS FIX
// S360 HIGH RES PDF IMPORT UX
import { useRef, useState, type MouseEvent } from 'react';
import {
  renderPdfCrop,
  renderPdfFullPage,
  uploadPdfPreview,
  type PdfPreviewPage,
} from '../api/client';
import type { PdfCropInsertMeta } from '../model/types';

type InsertMode = 'page' | 'underlay' | 'newpage';
type Dpi = 300 | 400 | 600;

interface Props {
  projectId: string;
  onInsert: (url: string, name: string, meta: PdfCropInsertMeta, mode: InsertMode) => void;
  onCancel: () => void;
}

interface Rect { x: number; y: number; w: number; h: number }

// Import PDF Page / Crop — render a crisp region straight from the PDF at high DPI.
// The crop rectangle is drawn on a preview image and mapped back to PDF point
// coordinates so the output is vector-sharp, never a scaled screenshot.
export default function PdfCropModal({ projectId, onInsert, onCancel }: Props) {
  const [pages, setPages] = useState<PdfPreviewPage[]>([]);
  const [pdfFile, setPdfFile] = useState('');
  const [selected, setSelected] = useState(0);
  const [dpi, setDpi] = useState<Dpi>(400);
  const [autocrop, setAutocrop] = useState(false);
  const [mode, setMode] = useState<InsertMode>('page');
  const [loading, setLoading] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState('');
  const [rect, setRect] = useState<Rect | null>(null);
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const imgWrapRef = useRef<HTMLDivElement>(null);
  const previewImgRef = useRef<HTMLImageElement>(null);

  const page = pages[selected];

  const onFilePick = async (file: File) => {
    setError('');
    setLoading(true);
    try {
      const res = await uploadPdfPreview(projectId, file);
      setPages(res.pages);
      setPdfFile(res.pdfFile);
      setSelected(0);
      setRect(null);
      setPreviewUrl('');
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  // ── crop rectangle drawing on the preview image ──
  const localPoint = (clientX: number, clientY: number) => {
    const wrap = imgWrapRef.current;
    const image = previewImgRef.current;
    if (!wrap || !image) return { x: 0, y: 0 };
    const wrapBox = wrap.getBoundingClientRect();
    const imageBox = image.getBoundingClientRect();
    const imageLeft = imageBox.left - wrapBox.left;
    const imageTop = imageBox.top - wrapBox.top;
    return {
      x: imageLeft + Math.max(0, Math.min(clientX - imageBox.left, imageBox.width)),
      y: imageTop + Math.max(0, Math.min(clientY - imageBox.top, imageBox.height)),
    };
  };
  const onDown = (e: MouseEvent<HTMLDivElement>) => {
    const p = localPoint(e.clientX, e.clientY);
    setDrag(p);
    setRect({ x: p.x, y: p.y, w: 0, h: 0 });
    setPreviewUrl('');
  };
  const onMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!drag) return;
    const p = localPoint(e.clientX, e.clientY);
    setRect({ x: Math.min(drag.x, p.x), y: Math.min(drag.y, p.y), w: Math.abs(p.x - drag.x), h: Math.abs(p.y - drag.y) });
  };
  const onUp = () => setDrag(null);

  // Map the displayed-pixel crop rectangle back to PDF point coordinates.
  const clipPoints = () => {
    const wrap = imgWrapRef.current;
    const image = previewImgRef.current;
    if (!wrap || !image || !page) return null;
    const wrapBox = wrap.getBoundingClientRect();
    const imageBox = image.getBoundingClientRect();
    if (imageBox.width <= 0 || imageBox.height <= 0) return null;
    if (!rect || rect.w < 4 || rect.h < 4) return null; // treat as "whole page"
    const imageLeft = imageBox.left - wrapBox.left;
    const imageTop = imageBox.top - wrapBox.top;
    const x0px = Math.max(0, Math.min(rect.x - imageLeft, imageBox.width));
    const y0px = Math.max(0, Math.min(rect.y - imageTop, imageBox.height));
    const x1px = Math.max(x0px, Math.min(rect.x + rect.w - imageLeft, imageBox.width));
    const y1px = Math.max(y0px, Math.min(rect.y + rect.h - imageTop, imageBox.height));
    const sx = page.widthPt / imageBox.width;
    const sy = page.heightPt / imageBox.height;
    return {
      x0: x0px * sx,
      y0: y0px * sy,
      x1: x1px * sx,
      y1: y1px * sy,
    };
  };

  const render = async (): Promise<{ url: string; meta: PdfCropInsertMeta } | null> => {
    const clip = clipPoints();
    if (clip) {
      const res = await renderPdfCrop(projectId, { pdfFile, page: selected, dpi, clip, autocrop });
      const cp = res.meta.cropPoints;
      const meta: PdfCropInsertMeta = {
        pdfSource: pdfFile,
        pdfPage: selected,
        pdfDpi: dpi,
        pdfCrop: cp ? `${cp.x0.toFixed(1)},${cp.y0.toFixed(1)},${cp.x1.toFixed(1)},${cp.y1.toFixed(1)}` : undefined,
      };
      return { url: res.asset.url, meta };
    }
    // No crop drawn → render the whole page crisply.
    const res = await renderPdfFullPage(projectId, { pdfFile, page: selected, dpi });
    return { url: res.asset.url, meta: { pdfSource: pdfFile, pdfPage: selected, pdfDpi: dpi } };
  };

  const doRenderPreview = async () => {
    setError('');
    setRendering(true);
    try {
      const out = await render();
      if (out) setPreviewUrl(out.url);
    } catch (e) {
      setError(String(e));
    } finally {
      setRendering(false);
    }
  };

  const doInsert = async () => {
    setError('');
    setRendering(true);
    try {
      const out = await render();
      if (!out) return;
      const name = `PDF ${pdfFile.replace(/\.pdf$/i, '')} p${selected + 1}`;
      onInsert(out.url, name, out.meta, mode);
    } catch (e) {
      setError(String(e));
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal pdfcrop-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Import PDF Page / Crop</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          {!pages.length ? (
            <div className="field">
              <label htmlFor="pdfcrop-pick">Choose a PDF schematic</label>
              <label className="btn file-ribbon-btn" title="Upload a PDF and crop a crisp region to insert">
                {loading ? 'Loading…' : 'Select PDF…'}
                <input
                  id="pdfcrop-pick"
                  type="file"
                  accept="application/pdf"
                  disabled={loading}
                  onChange={(e) => e.target.files?.[0] && void onFilePick(e.target.files[0])}
                />
              </label>
              <p className="renumber-note pdf-insert-hint">
                <strong>Best quality:</strong> use PDF Page / Crop instead of screenshots.
                Regions are rendered straight from the PDF at 300–600 DPI so they
                stay sharp at 11×17 export.
              </p>
            </div>
          ) : (
            <div className="pdfcrop-layout">
              <div className="pdfcrop-pages">
                {pages.map((pg) => (
                  <button
                    key={pg.page}
                    className={`pdfcrop-pagebtn ${selected === pg.page ? 'active' : ''}`}
                    onClick={() => { setSelected(pg.page); setRect(null); setPreviewUrl(''); }}
                    title={`Page ${pg.page + 1} — ${pg.widthIn}" × ${pg.heightIn}"`}
                  >
                    <img src={pg.previewDataUrl} alt={`Page ${pg.page + 1}`} />
                    <span>{pg.page + 1}</span>
                  </button>
                ))}
              </div>

              <div className="pdfcrop-main">
                <div
                  className="pdfcrop-canvas"
                  ref={imgWrapRef}
                  onMouseDown={onDown}
                  onMouseMove={onMove}
                  onMouseUp={onUp}
                  onMouseLeave={onUp}
                >
                  {page && <img ref={previewImgRef} className="pdfcrop-preview-img" src={page.previewDataUrl} alt={`Page ${selected + 1}`} draggable={false} />}
                  {rect && rect.w > 2 && rect.h > 2 && (
                    <svg className="pdfcrop-overlay" aria-hidden="true">
                      <rect className="pdfcrop-rect" x={rect.x} y={rect.y} width={rect.w} height={rect.h} />
                    </svg>
                  )}
                </div>
                <p className="pdfcrop-hint">Drag a rectangle over the region (e.g. “Leak Alarm Controller”). No selection = whole page.</p>
              </div>

              <div className="pdfcrop-controls">
                <div className="field">
                  <label>Page</label>
                  <div className="pdfcrop-pageinfo">Page {selected + 1} of {pages.length}{page ? ` · ${page.widthIn}"×${page.heightIn}"` : ''}</div>
                </div>
                <div className="field">
                  <label htmlFor="pdfcrop-dpi">Resolution (DPI)</label>
                  <select id="pdfcrop-dpi" value={dpi} onChange={(e) => setDpi(Number(e.target.value) as Dpi)}>
                    <option value={300}>300 DPI</option>
                    <option value={400}>400 DPI</option>
                    <option value={600}>600 DPI</option>
                  </select>
                </div>
                <div className="field">
                  <label title="Trim residual white margins from the rendered crop">
                    <input type="checkbox" checked={autocrop} onChange={(e) => setAutocrop(e.target.checked)} /> Auto-crop whitespace
                  </label>
                </div>
                <div className="field">
                  <label htmlFor="pdfcrop-mode">Insert as</label>
                  <select id="pdfcrop-mode" value={mode} onChange={(e) => setMode(e.target.value as InsertMode)}>
                    <option value="page">Insert on current page</option>
                    <option value="underlay">Insert as locked underlay</option>
                    <option value="newpage" disabled>Create new page (coming soon)</option>
                  </select>
                  <p className="pdfcrop-disabled-hint">Create-new-page mode is intentionally disabled in this pass.</p>
                </div>
                {previewUrl && (
                  <div className="field pdfcrop-result">
                    <label>Rendered crop preview</label>
                    <img src={previewUrl} alt="Rendered crop" />
                  </div>
                )}
              </div>
            </div>
          )}
          {error && <p className="lib-error">{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          {pages.length > 0 && (
            <>
              <button className="btn" disabled={rendering} onClick={() => void doRenderPreview()}>
                {rendering ? 'Rendering…' : 'Render Preview'}
              </button>
              <button className="btn btn-primary" disabled={rendering} onClick={() => void doInsert()}>
                {rendering ? 'Rendering…' : 'Import PDF Crop'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
