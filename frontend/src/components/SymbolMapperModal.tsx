import { useMemo, useRef, useState, type PointerEvent } from 'react';
import {
  createSymbolMapperSession,
  detectSymbolMap,
  renderSymbolMap,
  type SymbolMapperCandidate,
  type SymbolMapperClass,
  type SymbolMapperDetection,
  type SymbolMapperRenderResult,
  type SymbolMapperSession,
} from '../api/client';

interface Props {
  onClose: () => void;
  onAddPage?: (result: SymbolMapperRenderResult, title: string) => Promise<void>;
}

type Step = 'upload' | 'configure' | 'review' | 'final';
type NormalizedBox = { x0: number; y0: number; x1: number; y1: number };

const COLORS = [
  '#ffd400', '#ff6b35', '#00a651', '#12539b', '#d71920', '#8e44ad',
  '#00a8cc', '#7f8c8d', '#e67e22', '#2c3e50', '#c0392b', '#16a085',
];

const PATTERNS: Array<{ value: SymbolMapperClass['pattern']; label: string }> = [
  { value: 'solid', label: 'Solid fill' },
  { value: 'outline', label: 'Outline only' },
  { value: 'double-outline', label: 'Double outline' },
  { value: 'split-vertical', label: 'Split vertical' },
  { value: 'split-horizontal', label: 'Split horizontal' },
  { value: 'diagonal', label: 'Diagonal stripe' },
  { value: 'crosshatch', label: 'Crosshatch' },
];

function nextId() {
  return `symbol_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function makeClass(index: number): SymbolMapperClass {
  return {
    id: nextId(),
    code: '',
    label: '',
    shape: 'auto',
    color: COLORS[index % COLORS.length],
    color2: COLORS[(index + 3) % COLORS.length],
    pattern: PATTERNS[Math.floor(index / COLORS.length) % PATTERNS.length].value,
    markerSizePt: 18,
    visualEnabled: true,
  };
}

function statusOf(candidate: SymbolMapperCandidate): 'accepted' | 'review' | 'rejected' {
  if (candidate.status === 'accepted' || candidate.status === 'rejected') return candidate.status;
  return candidate.accepted ? 'accepted' : 'review';
}

function displayScore(value: number) {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : '—';
}

export default function SymbolMapperModal({ onClose, onAddPage }: Props) {
  const [step, setStep] = useState<Step>('upload');
  const [session, setSession] = useState<SymbolMapperSession | null>(null);
  const [classes, setClasses] = useState<SymbolMapperClass[]>([makeClass(0)]);
  const [activeClassId, setActiveClassId] = useState<string>('');
  const [detection, setDetection] = useState<SymbolMapperDetection | null>(null);
  const [rendered, setRendered] = useState<SymbolMapperRenderResult | null>(null);
  const [pageTitle, setPageTitle] = useState('SYMBOL HIGHLIGHT PLAN');
  const [filterClass, setFilterClass] = useState('all');
  const [filterStatus, setFilterStatus] = useState<'all' | 'accepted' | 'review' | 'rejected'>('all');
  const [focusCandidateId, setFocusCandidateId] = useState('');
  const [zoom, setZoom] = useState(1);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragBox, setDragBox] = useState<NormalizedBox | null>(null);
  const [manualMode, setManualMode] = useState(false);
  const [manualClassId, setManualClassId] = useState('');
  const [manualStart, setManualStart] = useState<{ x: number; y: number } | null>(null);
  const [manualBox, setManualBox] = useState<NormalizedBox | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const configureImgRef = useRef<HTMLImageElement | null>(null);
  const reviewImgRef = useRef<HTMLImageElement | null>(null);
  const reviewFocusRef = useRef<HTMLDivElement | null>(null);

  const activeClass = classes.find((item) => item.id === activeClassId) ?? classes[0];

  const updateClass = (id: string, patch: Partial<SymbolMapperClass>) => {
    setClasses((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const addClass = () => {
    const next = makeClass(classes.length);
    setClasses((current) => [...current, next]);
    setActiveClassId(next.id);
  };

  const removeClass = (id: string) => {
    if (classes.length <= 1) return;
    const remaining = classes.filter((item) => item.id !== id);
    setClasses(remaining);
    if (activeClassId === id) setActiveClassId(remaining[0]?.id ?? '');
  };

  const pickFile = async (file: File) => {
    setError('');
    setLoading(true);
    try {
      const created = await createSymbolMapperSession(file);
      setSession(created);
      setStep('configure');
      setActiveClassId(classes[0]?.id ?? '');
      setDetection(null);
      setRendered(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const pointInImage = (event: PointerEvent<HTMLDivElement>) => {
    const img = configureImgRef.current;
    if (!img) return null;
    const bounds = img.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return null;
    const x = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    const y = Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height));
    return { x, y };
  };

  const beginCrop = (event: PointerEvent<HTMLDivElement>) => {
    if (!activeClass) return;
    const point = pointInImage(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart(point);
    setDragBox({ x0: point.x, y0: point.y, x1: point.x, y1: point.y });
  };

  const moveCrop = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    const point = pointInImage(event);
    if (!point) return;
    setDragBox({
      x0: Math.min(dragStart.x, point.x),
      y0: Math.min(dragStart.y, point.y),
      x1: Math.max(dragStart.x, point.x),
      y1: Math.max(dragStart.y, point.y),
    });
  };

  const finishCrop = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragStart || !dragBox || !activeClass) {
      setDragStart(null);
      setDragBox(null);
      return;
    }
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch { /* no-op */ }
    const width = dragBox.x1 - dragBox.x0;
    const height = dragBox.y1 - dragBox.y0;
    if (width >= 0.002 && height >= 0.002) {
      updateClass(activeClass.id, { templateBox: dragBox, visualEnabled: true });
    }
    setDragStart(null);
    setDragBox(null);
  };

  const runDetection = async () => {
    if (!session) return;
    const valid = classes.filter((item) => item.code.trim() || item.templateBox);
    if (!valid.length) {
      setError('Enter a printed symbol code or draw a tight legend crop for at least one row.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = await detectSymbolMap(session.id, valid);
      setClasses(valid);
      setDetection(result);
      setManualClassId(valid[0]?.id ?? '');
      setManualMode(false);
      setStep('review');
      const firstReview = result.candidates.find((candidate) => statusOf(candidate) === 'review');
      setFocusCandidateId(firstReview?.id ?? result.candidates[0]?.id ?? '');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const setCandidateStatus = (id: string, status: 'accepted' | 'review' | 'rejected') => {
    setDetection((current) => current ? {
      ...current,
      candidates: current.candidates.map((candidate) => candidate.id === id
        ? { ...candidate, status, accepted: status === 'accepted' }
        : candidate),
    } : current);
  };

  const pointInReview = (event: PointerEvent<HTMLDivElement>) => {
    const img = reviewImgRef.current;
    if (!img) return null;
    const bounds = img.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return null;
    const x = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    const y = Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height));
    return { x, y };
  };

  const beginManualMarker = (event: PointerEvent<HTMLDivElement>) => {
    if (!manualMode || !manualClassId) return;
    const point = pointInReview(event);
    if (!point) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setManualStart(point);
    setManualBox({ x0: point.x, y0: point.y, x1: point.x, y1: point.y });
  };

  const moveManualMarker = (event: PointerEvent<HTMLDivElement>) => {
    if (!manualMode || !manualStart) return;
    const point = pointInReview(event);
    if (!point) return;
    setManualBox({
      x0: Math.min(manualStart.x, point.x),
      y0: Math.min(manualStart.y, point.y),
      x1: Math.max(manualStart.x, point.x),
      y1: Math.max(manualStart.y, point.y),
    });
  };

  const finishManualMarker = (event: PointerEvent<HTMLDivElement>) => {
    if (!manualMode || !manualStart || !manualBox) {
      setManualStart(null);
      setManualBox(null);
      return;
    }
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch { /* no-op */ }
    const symbolClass = classes.find((item) => item.id === manualClassId);
    if (symbolClass) {
      const x0 = manualBox.x0 * pageW;
      const y0 = manualBox.y0 * pageH;
      const x1 = manualBox.x1 * pageW;
      const y1 = manualBox.y1 * pageH;
      const width = Math.max(0.5, x1 - x0);
      const height = Math.max(0.5, y1 - y0);
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      const side = Math.max(symbolClass.markerSizePt || 18, width + 5, height + 5);
      const candidate: SymbolMapperCandidate = {
        id: `manual_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        classId: symbolClass.id,
        code: symbolClass.code,
        label: symbolClass.label,
        bbox: [x0, y0, x1, y1],
        markerBox: [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2],
        method: 'manual',
        evidence: ['user-placed'],
        score: 1,
        status: 'accepted',
        accepted: true,
        shapeRect: null,
        text: '',
      };
      setDetection((current) => current ? { ...current, candidates: [...current.candidates, candidate] } : current);
      setFocusCandidateId(candidate.id);
    }
    setManualStart(null);
    setManualBox(null);
    setManualMode(false);
  };

  const visibleCandidates = useMemo(() => {
    const candidates = detection?.candidates ?? [];
    return candidates.filter((candidate) => {
      const classOk = filterClass === 'all' || candidate.classId === filterClass;
      const statusOk = filterStatus === 'all' || statusOf(candidate) === filterStatus;
      return classOk && statusOk;
    });
  }, [detection, filterClass, filterStatus]);

  const liveSummary = useMemo(() => classes.map((symbolClass) => {
    const items = (detection?.candidates ?? []).filter((candidate) => candidate.classId === symbolClass.id);
    return {
      classId: symbolClass.id,
      code: symbolClass.code,
      label: symbolClass.label,
      accepted: items.filter((candidate) => statusOf(candidate) === 'accepted').length,
      review: items.filter((candidate) => statusOf(candidate) === 'review').length,
      rejected: items.filter((candidate) => statusOf(candidate) === 'rejected').length,
      total: items.length,
    };
  }), [classes, detection]);

  const renderReviewed = async () => {
    if (!session || !detection) return;
    setError('');
    setLoading(true);
    try {
      const result = await renderSymbolMap(session.id, classes, detection.candidates);
      setRendered(result);
      setStep('final');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const addResultPage = async () => {
    if (!rendered || !onAddPage) return;
    const title = pageTitle.trim() || 'SYMBOL HIGHLIGHT PLAN';
    setError('');
    setLoading(true);
    try {
      await onAddPage(rendered, title);
      onClose();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const focusCandidate = (candidate: SymbolMapperCandidate) => {
    setFocusCandidateId(candidate.id);
    window.setTimeout(() => reviewFocusRef.current?.scrollIntoView({ block: 'center', inline: 'center' }), 0);
  };

  const focused = detection?.candidates.find((candidate) => candidate.id === focusCandidateId);
  const pageW = session?.page.widthPt || 1;
  const pageH = session?.page.heightPt || 1;

  return (
    <div className="symbol-mapper-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="symbol-mapper-shell" role="dialog" aria-modal="true" aria-label="Symbol Mapper">
        <header className="symbol-mapper-head">
          <div>
            <h2>Symbol Mapper</h2>
            <p>Upload one drawing page, define the symbol key, review every match, then export or add a titled Singh360 page.</p>
          </div>
          <button className="symbol-mapper-close" onClick={onClose} title="Close Symbol Mapper">×</button>
        </header>

        <nav className="symbol-mapper-steps" aria-label="Symbol Mapper steps">
          {(['upload', 'configure', 'review', 'final'] as Step[]).map((item, index) => (
            <button
              key={item}
              className={`${step === item ? 'active' : ''} ${(['upload', 'configure', 'review', 'final'] as Step[]).indexOf(step) > index ? 'done' : ''}`}
              disabled={(item === 'configure' && !session) || (item === 'review' && !detection) || (item === 'final' && !rendered)}
              onClick={() => setStep(item)}
            >
              {index + 1}. {item === 'upload' ? 'Upload' : item === 'configure' ? 'Key & Colors' : item === 'review' ? 'Review' : 'Output'}
            </button>
          ))}
        </nav>

        <main className="symbol-mapper-body">
          {step === 'upload' && (
            <div className="symbol-mapper-upload">
              <div className="symbol-mapper-upload-card">
                <div className="symbol-mapper-upload-icon">PDF</div>
                <h3>Choose one PDF page</h3>
                <p>The upload remains immutable. Symbol Mapper creates reviewed copies and never writes over the source file.</p>
                <label className="symbol-mapper-primary file-ribbon-btn">
                  {loading ? 'Reading PDF…' : 'Select single-page PDF'}
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    disabled={loading}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      event.currentTarget.value = '';
                      if (file) void pickFile(file);
                    }}
                  />
                </label>
                <div className="symbol-mapper-policy">
                  <strong>Acceptance rule:</strong> exact text plus an enclosing vector marker can be pre-accepted. Text-only and image-template-only candidates always require review.
                </div>
              </div>
            </div>
          )}

          {step === 'configure' && session && (
            <div className="symbol-mapper-configure">
              <aside className="symbol-mapper-class-panel">
                <div className="symbol-mapper-panel-title">
                  <div>
                    <h3>Symbol classes</h3>
                    <p>Enter the printed code. Select a row, then drag tightly around its legend icon in the drawing preview.</p>
                  </div>
                  <button className="symbol-mapper-secondary" onClick={addClass}>+ Add symbol</button>
                </div>

                <div className="symbol-mapper-class-list">
                  {classes.map((item, index) => (
                    <article
                      key={item.id}
                      className={`symbol-mapper-class-card ${activeClass?.id === item.id ? 'active' : ''}`}
                      onClick={() => setActiveClassId(item.id)}
                    >
                      <div className="symbol-mapper-class-card-head">
                        <span className="symbol-mapper-swatch" style={{ background: item.color }} />
                        <strong>{item.code || `Symbol ${index + 1}`}</strong>
                        <span className={`symbol-mapper-crop-state ${item.templateBox ? 'ready' : ''}`}>{item.templateBox ? 'Icon crop set' : 'No icon crop'}</span>
                        <button className="symbol-mapper-icon-button" disabled={classes.length <= 1} onClick={(event) => { event.stopPropagation(); removeClass(item.id); }} title="Remove symbol">×</button>
                      </div>

                      <div className="symbol-mapper-fields">
                        <label>
                          Printed code
                          <input value={item.code} onChange={(event) => updateClass(item.id, { code: event.target.value.trimStart() })} placeholder="CC" />
                        </label>
                        <label>
                          Description
                          <input value={item.label} onChange={(event) => updateClass(item.id, { label: event.target.value })} placeholder="RDM case controller" />
                        </label>
                        <label>
                          Expected source outline
                          <select value={item.shape} onChange={(event) => updateClass(item.id, { shape: event.target.value as SymbolMapperClass['shape'] })}>
                            <option value="auto">Auto</option>
                            <option value="circle">Circle</option>
                            <option value="square">Square</option>
                          </select>
                        </label>
                        <label>
                          Marker style
                          <select value={item.pattern} onChange={(event) => updateClass(item.id, { pattern: event.target.value as SymbolMapperClass['pattern'] })}>
                            {PATTERNS.map((pattern) => <option key={pattern.value} value={pattern.value}>{pattern.label}</option>)}
                          </select>
                        </label>
                        <label>
                          Primary color
                          <input type="color" value={item.color} onChange={(event) => updateClass(item.id, { color: event.target.value })} />
                        </label>
                        <label>
                          Secondary color
                          <input type="color" value={item.color2} onChange={(event) => updateClass(item.id, { color2: event.target.value })} />
                        </label>
                        <label>
                          Square marker size
                          <input type="number" min={8} max={72} step={1} value={item.markerSizePt} onChange={(event) => updateClass(item.id, { markerSizePt: Number(event.target.value) || 18 })} />
                        </label>
                        <label className="symbol-mapper-checkbox">
                          <input type="checkbox" checked={item.visualEnabled !== false} onChange={(event) => updateClass(item.id, { visualEnabled: event.target.checked })} />
                          Use icon crop for review candidates
                        </label>
                      </div>
                      {item.templateBox && (
                        <button className="symbol-mapper-link" onClick={(event) => { event.stopPropagation(); updateClass(item.id, { templateBox: undefined }); }}>Clear icon crop</button>
                      )}
                    </article>
                  ))}
                </div>
              </aside>

              <section className="symbol-mapper-preview-panel">
                <div className="symbol-mapper-preview-toolbar">
                  <div>
                    <strong>{session.sourceName}</strong>
                    <span>{Math.round(session.page.widthPt)} × {Math.round(session.page.heightPt)} pt · {session.page.hasText ? `${session.page.wordCount} text words` : 'flattened / no text layer'}</span>
                  </div>
                  <span className="symbol-mapper-instruction">Selected: <strong>{activeClass?.code || activeClass?.label || 'unnamed symbol'}</strong>. Drag a tight rectangle around only its icon.</span>
                </div>
                <div className="symbol-mapper-preview-scroll">
                  <div
                    className="symbol-mapper-crop-stage"
                    onPointerDown={beginCrop}
                    onPointerMove={moveCrop}
                    onPointerUp={finishCrop}
                    onPointerCancel={finishCrop}
                  >
                    <img ref={configureImgRef} src={session.previewUrl} alt="Uploaded PDF page" draggable={false} />
                    {classes.map((item) => item.templateBox && (
                      <div
                        key={item.id}
                        className={`symbol-mapper-template-box ${activeClass?.id === item.id ? 'active' : ''}`}
                        style={{
                          left: `${item.templateBox.x0 * 100}%`,
                          top: `${item.templateBox.y0 * 100}%`,
                          width: `${(item.templateBox.x1 - item.templateBox.x0) * 100}%`,
                          height: `${(item.templateBox.y1 - item.templateBox.y0) * 100}%`,
                          borderColor: item.color,
                        }}
                      >
                        <span style={{ background: item.color }}>{item.code || 'ICON'}</span>
                      </div>
                    ))}
                    {dragBox && (
                      <div
                        className="symbol-mapper-template-box drawing"
                        style={{
                          left: `${dragBox.x0 * 100}%`, top: `${dragBox.y0 * 100}%`,
                          width: `${(dragBox.x1 - dragBox.x0) * 100}%`,
                          height: `${(dragBox.y1 - dragBox.y0) * 100}%`,
                        }}
                      />
                    )}
                  </div>
                </div>
              </section>
            </div>
          )}

          {step === 'review' && session && detection && (
            <div className="symbol-mapper-review">
              <section className="symbol-mapper-review-preview">
                <div className="symbol-mapper-preview-toolbar">
                  <div>
                    <strong>Detection review</strong>
                    <span>Colored = accepted. Gray corner marker = review required. Rejected items are omitted.</span>
                  </div>
                  <label className="symbol-mapper-zoom">Zoom <input type="range" min="0.5" max="3" step="0.1" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /> {Math.round(zoom * 100)}%</label>
                </div>
                <div className="symbol-mapper-review-scroll">
                  <div
                    className={`symbol-mapper-review-stage ${manualMode ? 'manual-mode' : ''}`}
                    style={{ width: `${zoom * 100}%` }}
                    onPointerDown={beginManualMarker}
                    onPointerMove={moveManualMarker}
                    onPointerUp={finishManualMarker}
                    onPointerCancel={finishManualMarker}
                  >
                    <img ref={reviewImgRef} src={detection.reviewPngUrl} alt="Detection review" draggable={false} />
                    {manualBox && (
                      <div
                        className="symbol-mapper-manual-box"
                        style={{
                          left: `${manualBox.x0 * 100}%`,
                          top: `${manualBox.y0 * 100}%`,
                          width: `${(manualBox.x1 - manualBox.x0) * 100}%`,
                          height: `${(manualBox.y1 - manualBox.y0) * 100}%`,
                        }}
                      />
                    )}
                    {focused && (
                      <div
                        ref={reviewFocusRef}
                        className="symbol-mapper-focus-box"
                        style={{
                          left: `${(focused.markerBox[0] / pageW) * 100}%`,
                          top: `${(focused.markerBox[1] / pageH) * 100}%`,
                          width: `${((focused.markerBox[2] - focused.markerBox[0]) / pageW) * 100}%`,
                          height: `${((focused.markerBox[3] - focused.markerBox[1]) / pageH) * 100}%`,
                        }}
                      />
                    )}
                  </div>
                </div>
              </section>

              <aside className="symbol-mapper-review-panel">
                <div className="symbol-mapper-summary-grid">
                  {liveSummary.map((row) => (
                    <button key={row.classId} className={filterClass === row.classId ? 'active' : ''} onClick={() => setFilterClass(filterClass === row.classId ? 'all' : row.classId)}>
                      <strong>{row.code || 'ICON'}</strong>
                      <span>{row.accepted} accepted · {row.review} review · {row.rejected} rejected</span>
                    </button>
                  ))}
                </div>

                {detection.warnings.map((warning) => <div className="symbol-mapper-warning" key={warning}>{warning}</div>)}

                <div className="symbol-mapper-manual-tools">
                  <select value={manualClassId} onChange={(event) => setManualClassId(event.target.value)}>
                    {classes.map((item) => <option key={item.id} value={item.id}>{item.code || item.label || 'Icon'}</option>)}
                  </select>
                  <button
                    className={`symbol-mapper-secondary ${manualMode ? 'active' : ''}`}
                    disabled={!manualClassId}
                    onClick={() => { setManualMode((value) => !value); setManualStart(null); setManualBox(null); }}
                  >
                    {manualMode ? 'Cancel manual marker' : 'Add missing marker'}
                  </button>
                  <span>{manualMode ? 'Drag tightly around the missed symbol on the drawing. The marker will be accepted and included.' : 'Use this for a symbol the detector missed.'}</span>
                </div>

                <div className="symbol-mapper-review-filters">
                  <select value={filterClass} onChange={(event) => setFilterClass(event.target.value)}>
                    <option value="all">All symbols</option>
                    {classes.map((item) => <option key={item.id} value={item.id}>{item.code || item.label || 'Icon'}</option>)}
                  </select>
                  <select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value as typeof filterStatus)}>
                    <option value="all">All states</option>
                    <option value="accepted">Accepted</option>
                    <option value="review">Needs review</option>
                    <option value="rejected">Rejected</option>
                  </select>
                  <button className="symbol-mapper-secondary" onClick={() => visibleCandidates.forEach((candidate) => setCandidateStatus(candidate.id, 'accepted'))}>Accept visible</button>
                  <button className="symbol-mapper-secondary" onClick={() => visibleCandidates.forEach((candidate) => setCandidateStatus(candidate.id, 'rejected'))}>Reject visible</button>
                </div>

                <div className="symbol-mapper-candidate-list">
                  {visibleCandidates.map((candidate) => {
                    const status = statusOf(candidate);
                    return (
                      <article key={candidate.id} className={`symbol-mapper-candidate ${status} ${focusCandidateId === candidate.id ? 'focused' : ''}`} onClick={() => focusCandidate(candidate)}>
                        <div>
                          <strong>{candidate.code || candidate.label || 'Icon'}</strong>
                          <span>{candidate.method} · {displayScore(candidate.score)}</span>
                          <small>{candidate.evidence.join(' + ')}</small>
                        </div>
                        <div className="symbol-mapper-status-actions" onClick={(event) => event.stopPropagation()}>
                          <button className={status === 'accepted' ? 'active' : ''} onClick={() => setCandidateStatus(candidate.id, 'accepted')} title="Accept">✓</button>
                          <button className={status === 'review' ? 'active' : ''} onClick={() => setCandidateStatus(candidate.id, 'review')} title="Leave for review">?</button>
                          <button className={status === 'rejected' ? 'active' : ''} onClick={() => setCandidateStatus(candidate.id, 'rejected')} title="Reject">×</button>
                        </div>
                      </article>
                    );
                  })}
                  {!visibleCandidates.length && <p className="symbol-mapper-empty">No candidates match these filters.</p>}
                </div>
              </aside>
            </div>
          )}

          {step === 'final' && rendered && (
            <div className="symbol-mapper-final">
              <section className="symbol-mapper-final-preview">
                <img src={rendered.pngUrl} alt="Reviewed symbol map" />
              </section>
              <aside className="symbol-mapper-final-panel">
                <h3>Reviewed output ready</h3>
                <dl>
                  <div><dt>Accepted highlights</dt><dd>{rendered.acceptedCount}</dd></div>
                  <div><dt>Still unreviewed</dt><dd>{rendered.reviewCount}</dd></div>
                  <div><dt>Rejected</dt><dd>{rendered.rejectedCount}</dd></div>
                  <div><dt>Source integrity</dt><dd>Verified</dd></div>
                </dl>
                <p>Only accepted detections are in the output. The direct download keeps the uploaded PDF page size and underlying drawing content.</p>
                <a className="symbol-mapper-primary" href={rendered.pdfUrl} download>Download original-size PDF</a>
                <a className="symbol-mapper-secondary symbol-mapper-download" href={rendered.pngUrl} download>Download rendered PNG</a>
                {onAddPage && (
                  <div className="symbol-mapper-add-page">
                    <label>
                      Singh360 page title
                      <input value={pageTitle} onChange={(event) => setPageTitle(event.target.value)} />
                    </label>
                    <button className="symbol-mapper-primary" disabled={loading} onClick={() => void addResultPage()}>
                      {loading ? 'Adding page…' : 'Add reviewed page at end'}
                    </button>
                    <small>The new page is included, uses sheet code NEW, receives the standard title block, and triggers the existing renumber reminder. You can move, copy, exclude, or delete it later.</small>
                  </div>
                )}
              </aside>
            </div>
          )}
        </main>

        {error && <div className="symbol-mapper-error">{error}</div>}

        <footer className="symbol-mapper-foot">
          <div>
            {session && <span>Session {session.id.slice(0, 8)} · source SHA-256 {session.sourceSha256.slice(0, 12)}…</span>}
          </div>
          <div className="symbol-mapper-foot-actions">
            {step !== 'upload' && <button className="symbol-mapper-secondary" disabled={loading} onClick={() => setStep(step === 'final' ? 'review' : step === 'review' ? 'configure' : 'upload')}>Back</button>}
            {step === 'configure' && <button className="symbol-mapper-primary" disabled={loading} onClick={() => void runDetection()}>{loading ? 'Detecting…' : 'Detect symbols'}</button>}
            {step === 'review' && <button className="symbol-mapper-primary" disabled={loading} onClick={() => void renderReviewed()}>{loading ? 'Rendering…' : 'Render accepted highlights'}</button>}
            <button className="symbol-mapper-secondary" onClick={onClose}>Close</button>
          </div>
        </footer>
      </section>
    </div>
  );
}
