// S360 PRECISION PDF CANVAS CROP V30
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react';
import {
  renderPdfCrop,
  renderPdfFullPage,
  uploadPdfPreview,
  type PdfPreviewPage,
} from '../api/client';
import type { PdfCropInsertMeta } from '../model/types';

type InsertMode = 'page' | 'underlay' | 'newpage';
type Dpi = 300 | 400 | 600;
type Tool = 'crop' | 'pan';
type ResizeHandle = 'nw' | 'ne' | 'sw' | 'se';

interface Props {
  projectId: string;
  initialFileUrl?: string;
  onInsert: (
    url: string,
    name: string,
    meta: PdfCropInsertMeta,
    mode: InsertMode,
  ) => void;
  onCancel: () => void;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

type Interaction =
  | {
      kind: 'draw';
      pointerId: number;
      start: { x: number; y: number };
    }
  | {
      kind: 'move';
      pointerId: number;
      start: { x: number; y: number };
      startRect: Rect;
    }
  | {
      kind: 'resize';
      pointerId: number;
      handle: ResizeHandle;
      start: { x: number; y: number };
      startRect: Rect;
    }
  | {
      kind: 'pan';
      pointerId: number;
      clientX: number;
      clientY: number;
      scrollLeft: number;
      scrollTop: number;
    };

const MIN_ZOOM = 0.08;
const MAX_ZOOM = 8;
const MIN_CROP = 4;

const clamp = (value: number, low: number, high: number) =>
  Math.min(high, Math.max(low, value));

const cleanRect = (rect: Rect, page: PdfPreviewPage): Rect => {
  const x = clamp(rect.x, 0, Math.max(0, page.previewWidth - MIN_CROP));
  const y = clamp(rect.y, 0, Math.max(0, page.previewHeight - MIN_CROP));
  const w = clamp(rect.w, MIN_CROP, page.previewWidth - x);
  const h = clamp(rect.h, MIN_CROP, page.previewHeight - y);
  return { x, y, w, h };
};

export default function PdfCropModal({
  projectId,
  initialFileUrl,
  onInsert,
  onCancel,
}: Props) {
  const [pages, setPages] = useState<PdfPreviewPage[]>([]);
  const [pdfFile, setPdfFile] = useState('');
  const [selected, setSelected] = useState(0);
  const [dpi, setDpi] = useState<Dpi>(400);
  const [autocrop, setAutocrop] = useState(false);
  const [mode, setMode] = useState<InsertMode>('page');
  const [tool, setTool] = useState<Tool>('crop');
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState('');
  const [rect, setRect] = useState<Rect | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [spacePan, setSpacePan] = useState(false);

  const viewportRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const interactionRef = useRef<Interaction | null>(null);
  const initialLoadStarted = useRef(false);

  const page = pages.find((item) => item.page === selected) ?? pages[0];

  const onFilePick = useCallback(async (file: File) => {
    if (
      file.type !== 'application/pdf'
      && !file.name.toLowerCase().endsWith('.pdf')
    ) {
      setError('Choose a PDF file.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await uploadPdfPreview(projectId, file);
      setPages(res.pages);
      setPdfFile(res.pdfFile);
      setSelected(res.pages[0]?.page ?? 0);
      setRect(null);
      setPreviewUrl('');
      setTool('crop');
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!initialFileUrl || initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    setLoading(true);
    fetch(initialFileUrl)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Project PDF could not be opened (${response.status}).`);
        const disposition = response.headers.get('content-disposition') || '';
        const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
        const basic = disposition.match(/filename="?([^";]+)"?/i)?.[1];
        const name = encoded ? decodeURIComponent(encoded) : basic || 'project.pdf';
        const blob = await response.blob();
        await onFilePick(new File([blob], name, { type: blob.type || 'application/pdf' }));
      })
      .catch((reason) => {
        setError(String(reason));
        setLoading(false);
      });
  }, [initialFileUrl, onFilePick]);

  const zoomCentered = useCallback((nextValue: number) => {
    const viewport = viewportRef.current;
    const next = clamp(nextValue, MIN_ZOOM, MAX_ZOOM);
    if (!viewport) {
      setZoom(next);
      return;
    }
    const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / zoom;
    const centerY = (viewport.scrollTop + viewport.clientHeight / 2) / zoom;
    setZoom(next);
    window.requestAnimationFrame(() => {
      viewport.scrollLeft = centerX * next - viewport.clientWidth / 2;
      viewport.scrollTop = centerY * next - viewport.clientHeight / 2;
    });
  }, [zoom]);

  const fitPage = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || !page) return;
    const availableW = Math.max(100, viewport.clientWidth - 34);
    const availableH = Math.max(100, viewport.clientHeight - 34);
    const next = clamp(
      Math.min(
        availableW / page.previewWidth,
        availableH / page.previewHeight,
      ),
      MIN_ZOOM,
      MAX_ZOOM,
    );
    setZoom(next);
    window.requestAnimationFrame(() => {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
    });
  }, [page]);

  const fitWidth = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || !page) return;
    const next = clamp(
      Math.max(100, viewport.clientWidth - 34) / page.previewWidth,
      MIN_ZOOM,
      MAX_ZOOM,
    );
    setZoom(next);
    window.requestAnimationFrame(() => {
      viewport.scrollLeft = 0;
    });
  }, [page]);

  useEffect(() => {
    if (!page) return;
    setRect(null);
    setPreviewUrl('');
    const timer = window.setTimeout(fitPage, 40);
    return () => window.clearTimeout(timer);
  }, [page?.page, fitPage]);

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code === 'Space' && !event.repeat) {
        event.preventDefault();
        setSpacePan(true);
      }
      if (event.key === 'Escape') {
        interactionRef.current = null;
      }
    };
    const up = (event: KeyboardEvent) => {
      if (event.code === 'Space') setSpacePan(false);
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  const pointFromClient = (
    clientX: number,
    clientY: number,
  ): { x: number; y: number } => {
    const stage = stageRef.current;
    if (!stage || !page) return { x: 0, y: 0 };
    const box = stage.getBoundingClientRect();
    return {
      x: clamp((clientX - box.left) / zoom, 0, page.previewWidth),
      y: clamp((clientY - box.top) / zoom, 0, page.previewHeight),
    };
  };

  const beginPan = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.setPointerCapture(event.pointerId);
    interactionRef.current = {
      kind: 'pan',
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
  };

  const beginDraw = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (!page) return;
    const viewport = viewportRef.current;
    viewport?.setPointerCapture(event.pointerId);
    const start = pointFromClient(event.clientX, event.clientY);
    interactionRef.current = {
      kind: 'draw',
      pointerId: event.pointerId,
      start,
    };
    setRect({ x: start.x, y: start.y, w: MIN_CROP, h: MIN_CROP });
    setPreviewUrl('');
  };

  const onStagePointerDown = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (
      event.button === 1
      || tool === 'pan'
      || spacePan
    ) {
      event.preventDefault();
      beginPan(event);
      return;
    }
    if (event.button !== 0) return;
    event.preventDefault();
    beginDraw(event);
  };

  const beginMove = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (!rect) return;
    event.preventDefault();
    event.stopPropagation();
    viewportRef.current?.setPointerCapture(event.pointerId);
    interactionRef.current = {
      kind: 'move',
      pointerId: event.pointerId,
      start: pointFromClient(event.clientX, event.clientY),
      startRect: rect,
    };
  };

  const beginResize = (
    event: ReactPointerEvent<HTMLButtonElement>,
    handle: ResizeHandle,
  ) => {
    if (!rect) return;
    event.preventDefault();
    event.stopPropagation();
    viewportRef.current?.setPointerCapture(event.pointerId);
    interactionRef.current = {
      kind: 'resize',
      pointerId: event.pointerId,
      handle,
      start: pointFromClient(event.clientX, event.clientY),
      startRect: rect,
    };
  };

  const onViewportPointerMove = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    const interaction = interactionRef.current;
    const viewport = viewportRef.current;
    if (
      !interaction
      || interaction.pointerId !== event.pointerId
      || !page
      || !viewport
    ) return;

    if (interaction.kind === 'pan') {
      viewport.scrollLeft =
        interaction.scrollLeft - (event.clientX - interaction.clientX);
      viewport.scrollTop =
        interaction.scrollTop - (event.clientY - interaction.clientY);
      return;
    }

    const point = pointFromClient(event.clientX, event.clientY);

    if (interaction.kind === 'draw') {
      const next = {
        x: Math.min(interaction.start.x, point.x),
        y: Math.min(interaction.start.y, point.y),
        w: Math.abs(point.x - interaction.start.x),
        h: Math.abs(point.y - interaction.start.y),
      };
      setRect(cleanRect(next, page));
      return;
    }

    if (interaction.kind === 'move') {
      const dx = point.x - interaction.start.x;
      const dy = point.y - interaction.start.y;
      const next = {
        ...interaction.startRect,
        x: clamp(
          interaction.startRect.x + dx,
          0,
          page.previewWidth - interaction.startRect.w,
        ),
        y: clamp(
          interaction.startRect.y + dy,
          0,
          page.previewHeight - interaction.startRect.h,
        ),
      };
      setRect(next);
      return;
    }

    const start = interaction.startRect;
    let x0 = start.x;
    let y0 = start.y;
    let x1 = start.x + start.w;
    let y1 = start.y + start.h;

    if (interaction.handle.includes('n')) y0 = point.y;
    if (interaction.handle.includes('s')) y1 = point.y;
    if (interaction.handle.includes('w')) x0 = point.x;
    if (interaction.handle.includes('e')) x1 = point.x;

    const next = {
      x: Math.min(x0, x1),
      y: Math.min(y0, y1),
      w: Math.abs(x1 - x0),
      h: Math.abs(y1 - y0),
    };
    setRect(cleanRect(next, page));
  };

  const endInteraction = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (interactionRef.current?.pointerId === event.pointerId) {
      interactionRef.current = null;
      try {
        viewportRef.current?.releasePointerCapture(event.pointerId);
      } catch {
        /* pointer capture may already be released */
      }
    }
  };

  const onWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.14 : 1 / 1.14;
    zoomCentered(zoom * factor);
  };

  const clipPoints = () => {
    if (!page || !rect || rect.w < MIN_CROP || rect.h < MIN_CROP) {
      return null;
    }
    const sx = page.widthPt / page.previewWidth;
    const sy = page.heightPt / page.previewHeight;
    return {
      x0: rect.x * sx,
      y0: rect.y * sy,
      x1: (rect.x + rect.w) * sx,
      y1: (rect.y + rect.h) * sy,
    };
  };

  const cropInches = rect && page
    ? {
        x: (rect.x / page.previewWidth) * page.widthIn,
        y: (rect.y / page.previewHeight) * page.heightIn,
        w: (rect.w / page.previewWidth) * page.widthIn,
        h: (rect.h / page.previewHeight) * page.heightIn,
      }
    : null;

  const updateInches = (
    field: 'x' | 'y' | 'w' | 'h',
    value: number,
  ) => {
    if (!page) return;
    const current = cropInches ?? {
      x: 0,
      y: 0,
      w: page.widthIn,
      h: page.heightIn,
    };
    const nextInches = { ...current, [field]: Math.max(0, value || 0) };
    const next = cleanRect(
      {
        x: (nextInches.x / page.widthIn) * page.previewWidth,
        y: (nextInches.y / page.heightIn) * page.previewHeight,
        w: (nextInches.w / page.widthIn) * page.previewWidth,
        h: (nextInches.h / page.heightIn) * page.previewHeight,
      },
      page,
    );
    setRect(next);
    setPreviewUrl('');
  };

  const render = async (): Promise<{
    url: string;
    meta: PdfCropInsertMeta;
  } | null> => {
    const clip = clipPoints();
    if (clip) {
      const res = await renderPdfCrop(projectId, {
        pdfFile,
        page: selected,
        dpi,
        clip,
        autocrop,
      });
      const cp = res.meta.cropPoints;
      return {
        url: res.asset.url,
        meta: {
          pdfSource: pdfFile,
          pdfPage: selected,
          pdfDpi: dpi,
          pdfCrop: cp
            ? `${cp.x0.toFixed(1)},${cp.y0.toFixed(1)},${cp.x1.toFixed(1)},${cp.y1.toFixed(1)}`
            : undefined,
        },
      };
    }

    const res = await renderPdfFullPage(projectId, {
      pdfFile,
      page: selected,
      dpi,
    });
    return {
      url: res.asset.url,
      meta: {
        pdfSource: pdfFile,
        pdfPage: selected,
        pdfDpi: dpi,
      },
    };
  };

  const doRenderPreview = async () => {
    setError('');
    setRendering(true);
    try {
      const out = await render();
      if (out) setPreviewUrl(out.url);
    } catch (reason) {
      setError(String(reason));
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
    } catch (reason) {
      setError(String(reason));
    } finally {
      setRendering(false);
    }
  };

  const clearSelection = () => {
    setRect(null);
    setPreviewUrl('');
  };

  const selectWholePage = () => {
    if (!page) return;
    setRect({
      x: 0,
      y: 0,
      w: page.previewWidth,
      h: page.previewHeight,
    });
    setPreviewUrl('');
  };

  const stageCursor =
    tool === 'pan' || spacePan
      ? 'grab'
      : 'crosshair';

  return (
    <div
      className="modal-backdrop pdfcrop-backdrop-v30"
      onClick={onCancel}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
      }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        const file = event.dataTransfer.files?.[0];
        if (file) void onFilePick(file);
      }}
    >
      <div
        className="modal pdfcrop-modal-v30"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="pdfcrop-head-v30">
          <div>
            <div className="pdfcrop-eyebrow-v30">PRECISION PDF CANVAS CROP</div>
            <h2>Drop a PDF, zoom in, pan, and crop the exact detail</h2>
            <p>
              Ctrl + mouse wheel zooms · Space or Pan tool drags the page ·
              crop corners resize · crop coordinates stay mapped to PDF points.
            </p>
          </div>
          <button type="button" className="modal-x" onClick={onCancel}>×</button>
        </header>

        {!pages.length ? (
          <main className="pdfcrop-drop-v30">
            <label
              htmlFor="pdfcrop-pick"
              className={`pdfcrop-dropzone-v30 ${loading ? 'loading' : ''}`}
            >
              <strong>{loading ? 'Loading PDF…' : 'Drop PDF here'}</strong>
              <span>or click to choose a PDF schematic</span>
              <small>
                The crop is rendered directly from the PDF at 300–600 DPI.
                It is not a screenshot.
              </small>
              <input
                id="pdfcrop-pick"
                type="file"
                accept="application/pdf,.pdf"
                disabled={loading}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void onFilePick(file);
                }}
              />
            </label>
            {error && <p className="lib-error">{error}</p>}
          </main>
        ) : (
          <>
            <div className="pdfcrop-toolbar-v30">
              <div className="pdfcrop-toolgroup-v30">
                <button
                  type="button"
                  className={tool === 'crop' ? 'active' : ''}
                  onClick={() => setTool('crop')}
                >
                  Crop
                </button>
                <button
                  type="button"
                  className={tool === 'pan' ? 'active' : ''}
                  onClick={() => setTool('pan')}
                >
                  Pan
                </button>
              </div>

              <div className="pdfcrop-toolgroup-v30">
                <button type="button" onClick={() => zoomCentered(zoom / 1.25)}>−</button>
                <button type="button" className="pdfcrop-zoom-readout-v30" onClick={() => zoomCentered(1)}>
                  {Math.round(zoom * 100)}%
                </button>
                <button type="button" onClick={() => zoomCentered(zoom * 1.25)}>+</button>
                <button type="button" onClick={fitPage}>Fit Page</button>
                <button type="button" onClick={fitWidth}>Fit Width</button>
                <button type="button" onClick={() => zoomCentered(1)}>100%</button>
                <button type="button" onClick={() => zoomCentered(2)}>200%</button>
                <button type="button" onClick={() => zoomCentered(4)}>400%</button>
              </div>

              <div className="pdfcrop-toolgroup-v30 pdfcrop-toolgroup-right-v30">
                <button type="button" onClick={clearSelection}>Clear Crop</button>
                <button type="button" onClick={selectWholePage}>Select Whole Page</button>
              </div>
            </div>

            <div className="pdfcrop-workspace-v30">
              <aside className="pdfcrop-pages-v30">
                {pages.map((item) => (
                  <button
                    key={item.page}
                    type="button"
                    className={selected === item.page ? 'active' : ''}
                    onClick={() => {
                      setSelected(item.page);
                      setRect(null);
                      setPreviewUrl('');
                    }}
                    title={`Page ${item.page + 1} — ${item.widthIn}" × ${item.heightIn}"`}
                  >
                    <img src={item.previewDataUrl} alt={`Page ${item.page + 1}`} />
                    <span>Page {item.page + 1}</span>
                  </button>
                ))}
              </aside>

              <main className="pdfcrop-main-v30">
                <div
                  className={`pdfcrop-viewport-v30 tool-${tool} ${spacePan ? 'space-pan' : ''}`}
                  ref={viewportRef}
                  onPointerMove={onViewportPointerMove}
                  onPointerUp={endInteraction}
                  onPointerCancel={endInteraction}
                  onWheel={onWheel}
                >
                  {page && (
                    <div
                      className="pdfcrop-stage-v30"
                      ref={stageRef}
                      style={{
                        width: page.previewWidth * zoom,
                        height: page.previewHeight * zoom,
                        cursor: stageCursor,
                      }}
                      onPointerDown={onStagePointerDown}
                    >
                      <img
                        src={page.previewDataUrl}
                        alt={`PDF page ${selected + 1}`}
                        draggable={false}
                      />

                      {rect && (
                        <div
                          className="pdfcrop-selection-v30"
                          style={{
                            left: rect.x * zoom,
                            top: rect.y * zoom,
                            width: rect.w * zoom,
                            height: rect.h * zoom,
                          }}
                          onPointerDown={beginMove}
                        >
                          <div className="pdfcrop-selection-label-v30">
                            {cropInches
                              ? `${cropInches.w.toFixed(2)}" × ${cropInches.h.toFixed(2)}"`
                              : 'Crop'}
                          </div>
                          {(['nw', 'ne', 'sw', 'se'] as ResizeHandle[]).map((handle) => (
                            <button
                              key={handle}
                              type="button"
                              className={`pdfcrop-handle-v30 ${handle}`}
                              aria-label={`Resize ${handle}`}
                              onPointerDown={(event) => beginResize(event, handle)}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div className="pdfcrop-status-v30">
                  <span>
                    {tool === 'crop'
                      ? 'Drag anywhere outside the crop to draw a new selection.'
                      : 'Drag to pan. Switch back to Crop to draw.'}
                  </span>
                  <span>
                    {rect && cropInches
                      ? `Crop: X ${cropInches.x.toFixed(2)}" · Y ${cropInches.y.toFixed(2)}" · ${cropInches.w.toFixed(2)}" × ${cropInches.h.toFixed(2)}"`
                      : 'No crop selected — import will use the whole page.'}
                  </span>
                </div>
              </main>

              <aside className="pdfcrop-controls-v30">
                <section>
                  <h3>PDF page</h3>
                  <p>
                    Page {selected + 1} of {pages.length}
                    {page ? ` · ${page.widthIn}" × ${page.heightIn}"` : ''}
                  </p>
                </section>

                <section>
                  <h3>Exact crop in inches</h3>
                  <div className="pdfcrop-number-grid-v30">
                    {(['x', 'y', 'w', 'h'] as const).map((field) => (
                      <label key={field}>
                        <span>{field.toUpperCase()}</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={
                            cropInches
                              ? cropInches[field].toFixed(2)
                              : ''
                          }
                          placeholder={field === 'x' || field === 'y' ? '0.00' : 'Whole page'}
                          onChange={(event) => {
                            const value = Number(event.target.value);
                            if (Number.isFinite(value)) updateInches(field, value);
                          }}
                        />
                      </label>
                    ))}
                  </div>
                </section>

                <section>
                  <h3>Output quality</h3>
                  <label>
                    Resolution
                    <select
                      value={dpi}
                      onChange={(event) => setDpi(Number(event.target.value) as Dpi)}
                    >
                      <option value={300}>300 DPI</option>
                      <option value={400}>400 DPI</option>
                      <option value={600}>600 DPI</option>
                    </select>
                  </label>
                  <label className="pdfcrop-check-v30">
                    <input
                      type="checkbox"
                      checked={autocrop}
                      onChange={(event) => setAutocrop(event.target.checked)}
                    />
                    Trim white space after rendering
                  </label>
                </section>

                <section>
                  <h3>Insert result</h3>
                  <label>
                    Insert as
                    <select
                      value={mode}
                      onChange={(event) => setMode(event.target.value as InsertMode)}
                    >
                      <option value="page">Editable image on current page</option>
                      <option value="underlay">Locked underlay</option>
                      <option value="newpage" disabled>Create new page — not enabled</option>
                    </select>
                  </label>
                </section>

                <section className="pdfcrop-preview-actions-v30">
                  <button
                    type="button"
                    disabled={rendering}
                    onClick={() => void doRenderPreview()}
                  >
                    {rendering ? 'Rendering…' : 'Render Crop Preview'}
                  </button>
                  <button
                    type="button"
                    className="primary"
                    disabled={rendering}
                    onClick={() => void doInsert()}
                  >
                    {rendering ? 'Rendering…' : 'Import Crop to Canvas'}
                  </button>
                </section>

                {previewUrl && (
                  <section className="pdfcrop-result-v30">
                    <h3>Rendered result</h3>
                    <img src={previewUrl} alt="Rendered PDF crop" />
                  </section>
                )}

                {error && <p className="lib-error">{error}</p>}
              </aside>
            </div>

            <footer className="pdfcrop-foot-v30">
              <button type="button" onClick={onCancel}>Cancel</button>
              <span>
                Crop coordinates are stored in PDF point space so save, reopen,
                duplication, and PDF export keep the same crisp region.
              </span>
              <button
                type="button"
                className="primary"
                disabled={rendering}
                onClick={() => void doInsert()}
              >
                {rendering ? 'Rendering…' : 'Import Crop to Canvas'}
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
