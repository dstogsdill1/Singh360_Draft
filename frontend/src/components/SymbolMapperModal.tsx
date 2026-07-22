import { useMemo, useState, type ChangeEvent, type KeyboardEvent, type MouseEvent } from 'react';
import {
  createSymbolMapperSession,
  detectSymbolMap,
  renderSymbolMap,
  saveSymbolMapperTemplate,
  type SymbolMapperCandidate,
  type SymbolMapperClass,
  type SymbolMapperDetection,
  type SymbolMapperLegendRow,
  type SymbolMapperRenderResult,
  type SymbolMapperSession,
  type SymbolMapperTemplate,
  type SymbolMapperTemplateSymbol,
} from '../api/client';
import {
  SYMBOL_PALETTE as PALETTE,
  normalizeSymbolTemplateText as normalizeTemplateText,
  paletteChoiceById,
  symbolMarkerStyle as markerVisualStyle,
  symbolTemplateKey as templateKey,
  type SymbolPaletteChoice as PaletteChoice,
} from '../model/symbolPalette';
import type { SymbolMapperCountPageRequest } from '../model/symbolCountSummary';

interface Props {
  onClose: () => void;
  onAddPage?: (result: SymbolMapperRenderResult, title: string, sheetCode: string, countPage: SymbolMapperCountPageRequest) => Promise<void>;
}

type Step = 'upload' | 'choose' | 'results' | 'output';


type ConfiguredSymbol = SymbolMapperClass & {
  enabled: boolean;
  paletteId: string;
  iconDataUrl: string;
  legendBox: { x0: number; y0: number; x1: number; y1: number };
  templateMatched: boolean;
};

function inferOutputFields(sourceName: string): { sheetCode: string; pageTitle: string } {
  const base = sourceName.replace(/\.pdf$/i, '').replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim();
  const withoutStore = base.replace(/^\d{2,6}\s+/, '').trim();
  const match = withoutStore.match(/\b([A-Z]{1,5})\s*[- ]\s*(\d+(?:\.\d+)?[A-Z]?)\b/i)
    ?? withoutStore.match(/\b([A-Z]{1,5})\s*(\d+\.\d+[A-Z]?)\b/i);
  if (!match) {
    return { sheetCode: 'NEW', pageTitle: withoutStore || 'SYMBOL HIGHLIGHT PLAN' };
  }
  const sheetCode = `${match[1].toUpperCase()}-${match[2]}`;
  const title = withoutStore.replace(match[0], sheetCode).trim();
  return { sheetCode, pageTitle: title || sheetCode };
}

function choiceForTemplate(item: SymbolMapperTemplateSymbol | undefined, index: number): PaletteChoice {
  const direct = item?.paletteId ? PALETTE.find((choice) => choice.id === item.paletteId) : undefined;
  if (direct) return direct;
  const inferred = item ? PALETTE.find((choice) => (
    choice.pattern === item.pattern
    && choice.color.toLowerCase() === item.color.toLowerCase()
    && choice.color2.toLowerCase() === item.color2.toLowerCase()
  )) : undefined;
  return inferred ?? paletteChoiceById(undefined, index);
}

function buildSymbols(rows: SymbolMapperLegendRow[], template: SymbolMapperTemplate): ConfiguredSymbol[] {
  const exact = new Map(template.symbols.map((item) => [templateKey(item.code, item.label), item]));
  const templateByCode = new Map<string, SymbolMapperTemplateSymbol[]>();
  for (const item of template.symbols) {
    const code = normalizeTemplateText(item.code);
    templateByCode.set(code, [...(templateByCode.get(code) ?? []), item]);
  }
  const rowCodeCounts = new Map<string, number>();
  for (const row of rows) {
    const code = normalizeTemplateText(row.code);
    rowCodeCounts.set(code, (rowCodeCounts.get(code) ?? 0) + 1);
  }

  return rows.map((row, index) => {
    const code = normalizeTemplateText(row.code);
    let saved = exact.get(templateKey(row.code, row.label));
    // Code-only fallback is allowed only when both the page and the saved standard
    // have one unambiguous row for that code. Duplicate codes such as S remain
    // separated by their descriptions.
    if (!saved && rowCodeCounts.get(code) === 1 && (templateByCode.get(code)?.length ?? 0) === 1) {
      saved = templateByCode.get(code)?.[0];
    }
    const choice = choiceForTemplate(saved, index);
    return {
      id: row.id,
      code: row.code,
      label: row.label,
      shape: saved?.shape ?? row.shape,
      color: saved?.color ?? choice.color,
      color2: saved?.color2 ?? choice.color2,
      pattern: saved?.pattern ?? choice.pattern,
      markerSizePt: row.markerSizePt,
      templateBox: row.templateBox,
      visualEnabled: false,
      enabled: saved?.enabled ?? true,
      paletteId: saved?.paletteId || choice.id,
      iconDataUrl: row.iconDataUrl,
      legendBox: row.legendBox,
      templateMatched: Boolean(saved),
    };
  });
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
  const [sheetCode, setSheetCode] = useState('NEW');
  const [addCountPage, setAddCountPage] = useState(true);
  const [countPageTitle, setCountPageTitle] = useState('SYMBOL COUNT SUMMARY');
  const [countSheetCode, setCountSheetCode] = useState('NEW');
  const [loading, setLoading] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [templateStatus, setTemplateStatus] = useState('');
  const [error, setError] = useState('');

  const active = symbols.find((item) => item.id === activeId) ?? symbols[0];
  const enabled = symbols.filter((item) => item.enabled);
  const reviewItems = useMemo(
    () => (detection?.candidates ?? []).filter((candidate) => statusOf(candidate) === 'review'),
    [detection],
  );
  // Count directly from the live reviewed candidate list. The backend summary is
  // the detection-time snapshot; these values stay accurate after Include/Ignore.
  const summary = useMemo(() => symbols.filter((item) => item.enabled).map((item) => {
    const matches = (detection?.candidates ?? []).filter((candidate) => candidate.classId === item.id);
    const accepted = matches.filter((candidate) => statusOf(candidate) === 'accepted').length;
    const review = matches.filter((candidate) => statusOf(candidate) === 'review').length;
    const rejected = matches.filter((candidate) => statusOf(candidate) === 'rejected').length;
    return { item, accepted, review, rejected, total: matches.length };
  }), [symbols, detection]);

  const countPageRows = useMemo(() => summary
    .filter(({ accepted }) => accepted > 0)
    .map(({ item, accepted, review, rejected, total }) => {
      const palette = PALETTE.find((choice) => choice.id === item.paletteId) ?? PALETTE[0];
      return {
        code: item.code,
        label: item.label,
        paletteLabel: palette.label,
        color: item.color,
        color2: item.color2,
        pattern: item.pattern,
        found: total,
        included: accepted,
        check: review,
        ignored: rejected,
      };
    }), [summary]);

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
      const outputFields = inferOutputFields(created.sourceName);
      setPageTitle(outputFields.pageTitle);
      setSheetCode(outputFields.sheetCode);
      setAddCountPage(true);
      setCountSheetCode('NEW');
      setCountPageTitle(outputFields.sheetCode !== 'NEW'
        ? `SYMBOL COUNT SUMMARY — ${outputFields.sheetCode}`
        : 'SYMBOL COUNT SUMMARY');
      const next = buildSymbols(created.legend.rows, created.template);
      setSymbols(next);
      setTemplateStatus(created.template.symbols.length
        ? `${created.template.name} loaded · ${created.template.symbols.length} saved symbols`
        : 'No saved standard yet. Choose colors and click Save standard.');
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

  const saveStandard = async () => {
    if (!symbols.length) return;
    setSavingTemplate(true);
    setError('');
    try {
      const payload: SymbolMapperTemplateSymbol[] = symbols.map((item) => ({
        key: templateKey(item.code, item.label),
        code: item.code,
        glyph: /\bCLEAN\s+SWITCH\b/i.test(item.label) ? '$' : item.code,
        label: item.label,
        shape: item.shape === 'auto' ? 'circle' : item.shape,
        enabled: item.enabled,
        paletteId: item.paletteId,
        color: item.color,
        color2: item.color2,
        pattern: item.pattern,
      }));
      const result = await saveSymbolMapperTemplate(payload);
      setSession((current) => current ? { ...current, template: result.template } : current);
      setSymbols((current) => current.map((item) => ({ ...item, templateMatched: true })));
      setTemplateStatus(`Standard updated · ${result.added} added · ${result.updated} updated · ${result.total} total`);
    } catch (err) {
      setError(String(err));
    } finally {
      setSavingTemplate(false);
    }
  };

  const runSelected = async () => {
    if (!session || !enabled.length) {
      setError('Choose at least one symbol.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const classes = enabled.map(({ enabled: _enabled, paletteId: _paletteId, iconDataUrl: _iconDataUrl, legendBox: _legendBox, templateMatched: _templateMatched, ...item }) => item);
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
      const classes = enabled.map(({ enabled: _enabled, paletteId: _paletteId, iconDataUrl: _iconDataUrl, legendBox: _legendBox, templateMatched: _templateMatched, ...item }) => item);
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
      const countPage: SymbolMapperCountPageRequest = {
        enabled: addCountPage,
        sheetCode: countSheetCode.trim() || 'NEW',
        pageTitle: countPageTitle.trim() || 'SYMBOL COUNT SUMMARY',
        rows: countPageRows,
      };
      await onAddPage(
        rendered,
        pageTitle.trim() || 'SYMBOL HIGHLIGHT PLAN',
        sheetCode.trim() || 'NEW',
        countPage,
      );
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
                    <p className="sm-template-status">{templateStatus}</p>
                  </div>
                  <div className="sm-list-actions">
                    <button onClick={() => selectAll(true)}>All</button>
                    <button onClick={() => selectAll(false)}>None</button>
                    <button className="sm-save-standard" disabled={savingTemplate || !symbols.length} onClick={() => void saveStandard()}>
                      {savingTemplate ? 'Saving…' : session.template.symbols.length ? 'Update standard' : 'Save standard'}
                    </button>
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
                          <i style={markerVisualStyle(selectedPalette, 0.24, 2)} />
                        </span>
                        <span className="sm-symbol-copy">
                          <strong>{item.code || 'SYMBOL'}</strong>
                          <small>{item.label}</small>
                          {!item.templateMatched && <em className="sm-new-symbol">New</em>}
                        </span>
                        <span className="sm-current-color" style={markerVisualStyle(selectedPalette, 0.72, 2)} title={selectedPalette.label} />
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
                        <span style={markerVisualStyle(choice, 1, 2)} />
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
                                ...markerVisualStyle(selectedPalette, 0.28, 2),
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
                  {summary.map(({ item, accepted, review, rejected, total }) => {
                    const selectedPalette = PALETTE.find((choice) => choice.id === item.paletteId) ?? PALETTE[0];
                    return (
                      <div key={item.id} className="sm-count-row">
                        <span style={markerVisualStyle(selectedPalette, 0.72, 2)} />
                        <div className="sm-count-copy"><strong>{item.code || 'SYMBOL'}</strong><small>{item.label}</small></div>
                        <div className="sm-count-metrics" aria-label={`${item.label} counts`}>
                          <span><b>{total}</b><small>found</small></span>
                          <span className="included"><b>{accepted}</b><small>included</small></span>
                          <span className={review ? 'check' : ''}><b>{review}</b><small>check</small></span>
                          <span><b>{rejected}</b><small>ignored</small></span>
                        </div>
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
                    <div className="sm-output-field-row">
                      <label>
                        Sheet code
                        <input value={sheetCode} onChange={(event: ChangeEvent<HTMLInputElement>) => setSheetCode(event.target.value)} />
                      </label>
                      <label>
                        Page title
                        <input value={pageTitle} onChange={(event: ChangeEvent<HTMLInputElement>) => setPageTitle(event.target.value)} />
                      </label>
                    </div>
                    <p className="sm-output-hint">These are read from the PDF filename when available. You can change either one before adding the page.</p>
                    <div className="sm-count-page-card">
                      <label className="sm-count-page-toggle">
                        <input type="checkbox" checked={addCountPage} onChange={(event: ChangeEvent<HTMLInputElement>) => setAddCountPage(event.target.checked)} />
                        <span>
                          <strong>Add a separate Symbol Count Summary page</strong>
                          <small>Option A · final Count equals Included. Zero-count and ignored symbols are omitted.</small>
                        </span>
                      </label>
                      {addCountPage && (
                        <>
                          <div className="sm-output-field-row sm-count-page-fields">
                            <label>
                              Summary sheet code
                              <input value={countSheetCode} onChange={(event: ChangeEvent<HTMLInputElement>) => setCountSheetCode(event.target.value)} />
                            </label>
                            <label>
                              Summary page title
                              <input value={countPageTitle} onChange={(event: ChangeEvent<HTMLInputElement>) => setCountPageTitle(event.target.value)} />
                            </label>
                          </div>
                          <div className="sm-count-page-preview">
                            <div className="sm-count-page-preview-head">
                              <strong>Included-symbol preview</strong>
                              <span>{countPageRows.reduce((sum, row) => sum + row.included, 0)} total</span>
                            </div>
                            {countPageRows.length ? (
                              <table>
                                <thead><tr><th>Symbol</th><th>Description</th><th>Count</th></tr></thead>
                                <tbody>
                                  {countPageRows.map((row) => (
                                    <tr key={`${row.code}-${row.label}`}>
                                      <td><i style={{ background: row.color }} />{row.code}</td>
                                      <td>{row.label}</td>
                                      <td>{row.included}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : <p>No included symbols were confirmed.</p>}
                          </div>
                        </>
                      )}
                    </div>
                    <button className="symbol-mapper-primary" disabled={loading} onClick={() => void addPage()}>
                      {loading ? 'Adding and saving…' : addCountPage ? 'Add highlighted + count pages' : 'Add highlighted page'}
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
