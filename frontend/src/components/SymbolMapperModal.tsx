import { useMemo, useState, type ChangeEvent, type KeyboardEvent, type MouseEvent } from 'react';
import {
  createSymbolMapperSession,
  detectSymbolMap,
  renderSymbolMap,
  type SymbolMapperCandidate,
  type SymbolMapperClass,
  type SymbolMapperDetection,
  type SymbolMapperLegendRow,
  type SymbolMapperRenderResult,
  type SymbolMapperSession,
} from '../api/client';

interface Props {
  onClose: () => void;
  onAddPage?: (result: SymbolMapperRenderResult, title: string) => Promise<void>;
}

type Step = 'upload' | 'choose' | 'results' | 'output';

type PaletteChoice = {
  id: string;
  label: string;
  color: string;
  color2: string;
  pattern: SymbolMapperClass['pattern'];
};

type ConfiguredSymbol = SymbolMapperClass & {
  enabled: boolean;
  paletteId: string;
  iconDataUrl: string;
  legendBox: { x0: number; y0: number; x1: number; y1: number };
};

const PALETTE: PaletteChoice[] = [
  { id: 'red', label: 'Red', color: '#e53935', color2: '#e53935', pattern: 'solid' },
  { id: 'green', label: 'Green', color: '#00a651', color2: '#00a651', pattern: 'solid' },
  { id: 'yellow', label: 'Yellow', color: '#ffd400', color2: '#ffd400', pattern: 'solid' },
  { id: 'blue', label: 'Blue', color: '#1e73be', color2: '#1e73be', pattern: 'solid' },
  { id: 'orange', label: 'Orange', color: '#ff7a00', color2: '#ff7a00', pattern: 'solid' },
  { id: 'purple', label: 'Purple', color: '#8e44ad', color2: '#8e44ad', pattern: 'solid' },
  { id: 'cyan', label: 'Cyan', color: '#00a8cc', color2: '#00a8cc', pattern: 'solid' },
  { id: 'pink', label: 'Pink', color: '#e84393', color2: '#e84393', pattern: 'solid' },
  { id: 'red-green', label: 'Red / Green', color: '#e53935', color2: '#00a651', pattern: 'split-vertical' },
  { id: 'red-blue', label: 'Red / Blue', color: '#e53935', color2: '#1e73be', pattern: 'split-vertical' },
  { id: 'yellow-blue', label: 'Yellow / Blue', color: '#ffd400', color2: '#1e73be', pattern: 'split-vertical' },
  { id: 'yellow-green', label: 'Yellow / Green', color: '#ffd400', color2: '#00a651', pattern: 'split-vertical' },
  { id: 'orange-blue', label: 'Orange / Blue', color: '#ff7a00', color2: '#1e73be', pattern: 'split-vertical' },
  { id: 'purple-green', label: 'Purple / Green', color: '#8e44ad', color2: '#00a651', pattern: 'split-vertical' },
  { id: 'red-yellow', label: 'Red / Yellow', color: '#e53935', color2: '#ffd400', pattern: 'split-vertical' },
  { id: 'blue-green', label: 'Blue / Green', color: '#1e73be', color2: '#00a651', pattern: 'split-vertical' },
];

function paletteBackground(choice: Pick<PaletteChoice, 'color' | 'color2' | 'pattern'>): string {
  return choice.pattern === 'split-vertical'
    ? `linear-gradient(90deg, ${choice.color} 0 50%, ${choice.color2} 50% 100%)`
    : choice.color;
}

function classFromLegend(row: SymbolMapperLegendRow, index: number): ConfiguredSymbol {
  const choice = PALETTE[index % PALETTE.length];
  return {
    id: row.id,
    code: row.code,
    label: row.label,
    shape: row.shape,
    color: choice.color,
    color2: choice.color2,
    pattern: choice.pattern,
    markerSizePt: row.markerSizePt,
    templateBox: row.templateBox,
    visualEnabled: false,
    enabled: true,
    paletteId: choice.id,
    iconDataUrl: row.iconDataUrl,
    legendBox: row.legendBox,
  };
}

function statusOf(candidate: SymbolMapperCandidate): 'accepted' | 'review' | 'rejected' {
  if (candidate.status === 'accepted' || candidate.status === 'rejected') return candidate.status;
  return candidate.accepted ? 'accepted' : 'review';
}

export default function SymbolMapperModal({ onClose, onAddPage }: Props) {
  const [step, setStep] = useState<Step>('upload');
  const [session, setSession] = useState<SymbolMapperSession | null>(null);
  const [symbols, setSymbols] = useState<ConfiguredSymbol[]>([]);
  const [activeId, setActiveId] = useState('');
  const [detection, setDetection] = useState<SymbolMapperDetection | null>(null);
  const [rendered, setRendered] = useState<SymbolMapperRenderResult | null>(null);
  const [pageTitle, setPageTitle] = useState('SYMBOL HIGHLIGHT PLAN');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const active = symbols.find((item) => item.id === activeId) ?? symbols[0];
  const enabled = symbols.filter((item) => item.enabled);
  const reviewItems = useMemo(
    () => (detection?.candidates ?? []).filter((candidate) => statusOf(candidate) === 'review'),
    [detection],
  );
  const summary = useMemo(() => symbols.map((item) => {
    const row = detection?.summary.find((entry) => entry.classId === item.id);
    return { item, accepted: row?.accepted ?? 0, review: row?.review ?? 0, total: row?.total ?? 0 };
  }).filter((entry) => entry.item.enabled), [symbols, detection]);

  const pickFile = async (file: File) => {
    setLoading(true);
    setError('');
    try {
      const created = await createSymbolMapperSession(file);
      setSession(created);
      setDetection(null);
      setRendered(null);
      if (!created.legend?.found || !created.legend.rows.length) {
        setSymbols([]);
        setActiveId('');
        setStep('choose');
        setError(created.legend?.message || 'No SYMBOL KEY was found on this page.');
        return;
      }
      const next = created.legend.rows.map(classFromLegend);
      setSymbols(next);
      setActiveId(next[0]?.id ?? '');
      setStep('choose');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const applyPalette = (paletteId: string) => {
    if (!active) return;
    const choice = PALETTE.find((item) => item.id === paletteId);
    if (!choice) return;
    setSymbols((current) => current.map((item) => item.id === active.id ? {
      ...item,
      paletteId: choice.id,
      color: choice.color,
      color2: choice.color2,
      pattern: choice.pattern,
    } : item));
  };

  const toggleSymbol = (id: string) => {
    setSymbols((current) => current.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item));
  };

  const selectAll = (value: boolean) => {
    setSymbols((current) => current.map((item) => ({ ...item, enabled: value })));
  };

  const runSelected = async () => {
    if (!session || !enabled.length) {
      setError('Choose at least one symbol.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const classes = enabled.map(({ enabled: _enabled, paletteId: _paletteId, iconDataUrl: _iconDataUrl, legendBox: _legendBox, ...item }) => item);
      const result = await detectSymbolMap(session.id, classes);
      setDetection(result);
      setStep('results');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const decideCandidate = (id: string, include: boolean) => {
    setDetection((current) => current ? {
      ...current,
      candidates: current.candidates.map((candidate) => candidate.id === id ? {
        ...candidate,
        status: include ? 'accepted' : 'rejected',
        accepted: include,
      } : candidate),
    } : current);
  };

  const decideAllReview = (include: boolean) => {
    setDetection((current) => current ? {
      ...current,
      candidates: current.candidates.map((candidate) => statusOf(candidate) === 'review' ? {
        ...candidate,
        status: include ? 'accepted' : 'rejected',
        accepted: include,
      } : candidate),
    } : current);
  };

  const createResult = async () => {
    if (!session || !detection) return;
    setLoading(true);
    setError('');
    try {
      const classes = enabled.map(({ enabled: _enabled, paletteId: _paletteId, iconDataUrl: _iconDataUrl, legendBox: _legendBox, ...item }) => item);
      const result = await renderSymbolMap(session.id, classes, detection.candidates);
      setRendered(result);
      setStep('output');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const addPage = async () => {
    if (!rendered || !onAddPage) return;
    setLoading(true);
    setError('');
    try {
      await onAddPage(rendered, pageTitle.trim() || 'SYMBOL HIGHLIGHT PLAN');
      onClose();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="symbol-mapper-backdrop">
      <section className="symbol-mapper-shell symbol-mapper-kiss" role="dialog" aria-modal="true" aria-label="Symbol Mapper">
        <header className="symbol-mapper-head">
          <div>
            <h2>Symbol Mapper</h2>
            <p>Pick the symbols. Pick the colors. Run it.</p>
          </div>
          <button className="symbol-mapper-close" onClick={onClose} title="Close">×</button>
        </header>

        <nav className="symbol-mapper-steps" aria-label="Steps">
          {([
            ['upload', '1. Upload'],
            ['choose', '2. Choose symbols'],
            ['results', '3. Check results'],
            ['output', '4. Save'],
          ] as Array<[Step, string]>).map(([value, label]) => (
            <button
              key={value}
              className={step === value ? 'active' : ''}
              disabled={(value === 'choose' && !session) || (value === 'results' && !detection) || (value === 'output' && !rendered)}
              onClick={() => setStep(value)}
            >
              {label}
            </button>
          ))}
        </nav>

        <main className="symbol-mapper-body">
          {step === 'upload' && (
            <div className="sm-simple-upload">
              <div className="sm-simple-upload-card">
                <div className="sm-pdf-badge">PDF</div>
                <h3>Upload one drawing page</h3>
                <p>Symbol Mapper will find the printed symbol key automatically. You do not draw boxes around individual symbols.</p>
                <label className="symbol-mapper-primary file-ribbon-btn">
                  {loading ? 'Reading symbol key…' : 'Choose PDF'}
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    disabled={loading}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const file = event.target.files?.[0];
                      event.currentTarget.value = '';
                      if (file) void pickFile(file);
                    }}
                  />
                </label>
              </div>
            </div>
          )}

          {step === 'choose' && session && (
            <div className="sm-choose-layout">
              <aside className="sm-symbol-list-panel">
                <div className="sm-panel-heading">
                  <div>
                    <h3>Which symbols do you want?</h3>
                    <p>{session.legend?.found ? session.legend.message : 'No symbol key found.'}</p>
                  </div>
                  <div className="sm-list-actions">
                    <button onClick={() => selectAll(true)}>All</button>
                    <button onClick={() => selectAll(false)}>None</button>
                  </div>
                </div>

                <div className="sm-symbol-list">
                  {symbols.map((item) => {
                    const selectedPalette = PALETTE.find((choice) => choice.id === item.paletteId) ?? PALETTE[0];
                    return (
                      <div
                        key={item.id}
                        className={`sm-symbol-row ${active?.id === item.id ? 'active' : ''} ${item.enabled ? '' : 'disabled'}`}
                        onClick={() => setActiveId(item.id)}
                        onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
                          if (event.key === 'Enter' || event.key === ' ') setActiveId(item.id);
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <label className="sm-check" onClick={(event: MouseEvent<HTMLLabelElement>) => event.stopPropagation()}>
                          <input type="checkbox" checked={item.enabled} onChange={() => toggleSymbol(item.id)} />
                        </label>
                        <span className="sm-icon-thumb">
                          {item.iconDataUrl && <img src={item.iconDataUrl} alt="" />}
                          <i style={{ background: paletteBackground(selectedPalette) }} />
                        </span>
                        <span className="sm-symbol-copy">
                          <strong>{item.code || 'SYMBOL'}</strong>
                          <small>{item.label}</small>
                        </span>
                        <span className="sm-current-color" style={{ background: paletteBackground(selectedPalette) }} title={selectedPalette.label} />
                      </div>
                    );
                  })}
                  {!symbols.length && (
                    <div className="sm-no-legend">
                      <strong>No symbol key was read.</strong>
                      <span>This page needs a printed heading such as SYMBOLS KEY or SYMBOL LEGEND.</span>
                    </div>
                  )}
                </div>
              </aside>

              <section className="sm-color-and-legend">
                <div className="sm-color-picker">
                  <div>
                    <h3>Color for {active?.code || 'selected symbol'}</h3>
                    <p>Click one. That is it.</p>
                  </div>
                  <div className="sm-palette-grid">
                    {PALETTE.map((choice) => (
                      <button
                        key={choice.id}
                        className={active?.paletteId === choice.id ? 'active' : ''}
                        disabled={!active}
                        onClick={() => applyPalette(choice.id)}
                        title={choice.label}
                      >
                        <span style={{ background: paletteBackground(choice) }} />
                        <small>{choice.label}</small>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="sm-legend-preview-panel">
                  <div className="sm-preview-title">
                    <div>
                      <h3>Symbol key preview</h3>
                      <p>The chosen colors are shown directly over the key.</p>
                    </div>
                    <strong>{enabled.length} selected</strong>
                  </div>
                  <div className="sm-legend-stage">
                    {session.legend?.previewDataUrl ? (
                      <div className="sm-legend-image-wrap">
                        <img src={session.legend.previewDataUrl} alt="Detected symbol key" />
                        {symbols.filter((item) => item.enabled).map((item) => {
                          const selectedPalette = PALETTE.find((choice) => choice.id === item.paletteId) ?? PALETTE[0];
                          return (
                            <span
                              key={item.id}
                              className="sm-legend-color-box"
                              style={{
                                left: `${item.legendBox.x0 * 100}%`,
                                top: `${item.legendBox.y0 * 100}%`,
                                width: `${(item.legendBox.x1 - item.legendBox.x0) * 100}%`,
                                height: `${(item.legendBox.y1 - item.legendBox.y0) * 100}%`,
                                background: paletteBackground(selectedPalette),
                              }}
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <div className="sm-no-legend">No legend preview is available.</div>
                    )}
                  </div>
                </div>
              </section>
            </div>
          )}

          {step === 'results' && session && detection && (
            <div className="sm-results-layout">
              <section className="sm-results-preview">
                <div className="sm-preview-title">
                  <div>
                    <h3>Highlighted drawing</h3>
                    <p>Colored boxes are ready. Gray boxes need one quick decision.</p>
                  </div>
                  <strong>{detection.candidates.filter((item) => statusOf(item) === 'accepted').length} ready</strong>
                </div>
                <div className="sm-results-image-scroll">
                  <img src={detection.reviewPngUrl} alt="Highlighted symbol review" />
                </div>
              </section>

              <aside className="sm-results-side">
                <div className="sm-count-list">
                  {summary.map(({ item, accepted, review, total }) => {
                    const selectedPalette = PALETTE.find((choice) => choice.id === item.paletteId) ?? PALETTE[0];
                    return (
                      <div key={item.id} className="sm-count-row">
                        <span style={{ background: paletteBackground(selectedPalette) }} />
                        <div><strong>{item.code || 'SYMBOL'}</strong><small>{item.label}</small></div>
                        <b>{accepted}</b>
                        {review > 0 && <em>+{review} check</em>}
                        {total === 0 && <em>none found</em>}
                      </div>
                    );
                  })}
                </div>

                <div className="sm-quick-check">
                  <div className="sm-quick-check-head">
                    <div>
                      <h3>Needs a quick check</h3>
                      <p>Only uncertain matches are listed here.</p>
                    </div>
                    <strong>{reviewItems.length}</strong>
                  </div>
                  {reviewItems.length > 0 && (
                    <div className="sm-review-all-actions">
                      <button onClick={() => decideAllReview(true)}>Include all</button>
                      <button onClick={() => decideAllReview(false)}>Ignore all</button>
                    </div>
                  )}
                  <div className="sm-review-items">
                    {reviewItems.map((candidate) => (
                      <div className="sm-review-item" key={candidate.id}>
                        <div><strong>{candidate.code || 'SYMBOL'}</strong><small>{candidate.label}</small></div>
                        <button className="keep" onClick={() => decideCandidate(candidate.id, true)}>Include</button>
                        <button onClick={() => decideCandidate(candidate.id, false)}>Ignore</button>
                      </div>
                    ))}
                    {!reviewItems.length && <div className="sm-all-clear">Nothing else needs a decision.</div>}
                  </div>
                </div>
              </aside>
            </div>
          )}

          {step === 'output' && rendered && (
            <div className="sm-output-layout">
              <section className="sm-output-preview">
                <img src={rendered.pngUrl} alt="Final highlighted drawing" />
              </section>
              <aside className="sm-output-actions">
                <h3>Done</h3>
                <p>{rendered.acceptedCount} highlights are in the final drawing.</p>
                <a className="symbol-mapper-primary sm-download" href={rendered.pdfUrl}>Download highlighted PDF</a>
                {onAddPage && (
                  <div className="sm-add-page-box">
                    <label>
                      Page title
                      <input value={pageTitle} onChange={(event: ChangeEvent<HTMLInputElement>) => setPageTitle(event.target.value)} />
                    </label>
                    <button className="symbol-mapper-primary" disabled={loading} onClick={() => void addPage()}>
                      Add page to Singh360
                    </button>
                  </div>
                )}
              </aside>
            </div>
          )}
        </main>

        {error && <div className="symbol-mapper-error">{error}</div>}

        <footer className="symbol-mapper-foot">
          <div className="sm-session-label">{session ? session.sourceName : 'No PDF loaded'}</div>
          <div className="sm-foot-actions">
            {step !== 'upload' && <button onClick={() => setStep(step === 'choose' ? 'upload' : step === 'results' ? 'choose' : 'results')}>Back</button>}
            {step === 'choose' && <button className="symbol-mapper-primary" disabled={loading || !enabled.length} onClick={() => void runSelected()}>{loading ? 'Finding symbols…' : 'Run selected symbols'}</button>}
            {step === 'results' && <button className="symbol-mapper-primary" disabled={loading} onClick={() => void createResult()}>{loading ? 'Creating page…' : 'Create highlighted page'}</button>}
            <button onClick={onClose}>Close</button>
          </div>
        </footer>
      </section>
    </div>
  );
}
