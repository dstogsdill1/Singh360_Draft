import { useMemo, useState, type DragEvent } from 'react';
import type { PageModel } from '../model/types';
import { classifyPageFamily, generateEmsCodes } from '../model/emsNumbering';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';

interface Props {
  pages: PageModel[];
  onApply: (updated: PageModel[]) => void;
  onCancel: () => void;
}

type Scheme = 'keep' | 'sequential' | 'prefix' | 'ems';

const CONT_SUFFIX = ['', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

/**
 * Preview + apply engineering sheet codes. Sheet codes are user-controlled and
 * separate from the auto "Page X of Y" package order. Continuation pages inherit
 * their base page's code with a letter suffix (4.0 -> 4.0a, 4.0b).
 */
export default function RenumberModal({ pages, onApply, onCancel }: Props) {
  // Default to "keep existing" (FINAL RENDER POLISH 4G, Phase A) — imported
  // sheet codes already come from the workbook/index Sheet Code column, so
  // opening this modal must never silently threaten to overwrite them with a
  // classification/sequential guess unless the user explicitly picks one.
  const [scheme, setScheme] = useState<Scheme>('keep');
  const [prefix, setPrefix] = useState('EMS');
  const [orderedPages, setOrderedPages] = useState<PageModel[]>(() => pages.map((page) => ({ ...page })));
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);

  const included = useMemo(() => orderedPages.filter((p) => p.include), [orderedPages]);

  // Compute proposed codes keyed by page id.
  const proposed = useMemo(() => {
    if (scheme === 'ems') {
      return generateEmsCodes(orderedPages, (prefix || 'EMS').trim());
    }
    const map = new Map<string, string>();
    // Base pages (non-continuation) get the running number; continuations inherit.
    const bases = included.filter((p) => !p.continuationOf);
    const baseCodeById = new Map<string, string>();
    let n = 0;
    for (const b of bases) {
      n += 1;
      let code: string;
      if (scheme === 'keep') {
        code = b.sheetCode || String(n);
      } else if (scheme === 'prefix') {
        code = `${prefix ? prefix + ' ' : ''}${n}.0`;
      } else {
        code = `${n}.0`;
      }
      baseCodeById.set(b.id, code);
      map.set(b.id, code);
    }
    // Continuations: base code + suffix by continuationIndex.
    for (const p of included) {
      if (!p.continuationOf) continue;
      const baseCode = baseCodeById.get(p.continuationOf) ?? p.sheetCode;
      if (scheme === 'keep') {
        map.set(p.id, p.sheetCode || baseCode);
      } else {
        const idx = Math.min(Math.max(p.continuationIndex ?? 1, 1), CONT_SUFFIX.length - 1);
        map.set(p.id, `${baseCode}${CONT_SUFFIX[idx]}`);
      }
    }
    return map;
  }, [orderedPages, included, scheme, prefix]);


  const reorderByDrop = (draggedId: string, targetId: string) => {
    const dragged = orderedPages.find((page) => page.id === draggedId);
    const target = orderedPages.find((page) => page.id === targetId);
    if (!dragged || !target || isCoverPage(dragged) || isSheetIndexPage(dragged) || isCoverPage(target) || isSheetIndexPage(target)) return;

    const draggedRoot = dragged.continuationOf || dragged.id;
    const targetRoot = target.continuationOf || target.id;
    if (draggedRoot === targetRoot) return;

    const movingIds = new Set(
      orderedPages
        .filter((page) => page.id === draggedRoot || page.continuationOf === draggedRoot)
        .map((page) => page.id),
    );
    const moving = orderedPages.filter((page) => movingIds.has(page.id));
    const remaining = orderedPages.filter((page) => !movingIds.has(page.id));
    const targetIndex = remaining.findIndex((page) => (page.continuationOf || page.id) === targetRoot);
    if (targetIndex < 0) return;

    const next = [...remaining];
    next.splice(targetIndex, 0, ...moving);
    setOrderedPages(next.map((page, index) => ({ ...page, order: index + 1 })));
  };

  const apply = () => {
    const updated = orderedPages.map((p) => {
      const code = proposed.get(p.id);
      if (code === undefined) return p;
      return { ...p, sheetCode: code, displaySheetCode: code };
    });
    onApply(updated);
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide renumber-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Renumber Sheet Codes</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          <div className="renumber-options">
            <label className={scheme === 'ems' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'ems'} onChange={() => { setScheme('ems'); setPrefix('EMS'); }} />
              EMS front matter + family (0.0, 0.1… then 1.x, 2.x, 3.x)
              <input
                className="prefix-input"
                type="text"
                placeholder="EMS"
                value={scheme === 'ems' ? prefix : ''}
                disabled={scheme !== 'ems'}
                onChange={(e) => setPrefix(e.target.value)}
                title="Prefix (EMS, RDM, REF…)"
              />
            </label>
            <label className={scheme === 'keep' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'keep'} onChange={() => setScheme('keep')} />
              Keep existing sheet codes
            </label>
            <label className={scheme === 'sequential' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'sequential'} onChange={() => setScheme('sequential')} />
              Sequential decimal (1.0, 2.0, 3.0…)
            </label>
            <label className={scheme === 'prefix' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'prefix'} onChange={() => { setScheme('prefix'); if (prefix === 'EMS') setPrefix(''); }} />
              Prefix + sequential
              <input
                className="prefix-input"
                type="text"
                placeholder="EMS"
                value={scheme === 'prefix' ? prefix : ''}
                disabled={scheme !== 'prefix'}
                onChange={(e) => setPrefix(e.target.value)}
              />
            </label>
            <p className="renumber-note">
              EMS numbering puts cover/index/directory/guidelines/scope/responsibility/BOM on a 0-series, then classifies technical sheets into families (2.x network, 3.x refrigeration, 5.x lighting, 8.x schematics…). Continuation pages inherit the base code (0.4a, 3.1a). “Page X of Y” is separate and follows the tab order. Drag any unlocked row below to fix the package order before applying.
            </p>
          </div>

          <table className="renumber-preview renumber-drag-table">
            <thead>
              <tr>
                <th className="renumber-order-col">Order</th>
                <th>Old Code</th>
                <th>New Code</th>
                <th>Sheet Title</th>
                <th>Page Family</th>
                <th>Included</th>
              </tr>
            </thead>
            <tbody>
              {orderedPages.map((p, index) => {
                const next = proposed.get(p.id) ?? p.sheetCode;
                const changed = p.include && next !== (p.sheetCode || '');
                const fam = classifyPageFamily(p);
                const locked = isCoverPage(p) || isSheetIndexPage(p);
                return (
                  <tr
                    key={p.id}
                    className={`${changed ? 'changed' : ''} ${dragOverId === p.id ? 'drag-over' : ''}`}
                    draggable={!locked}
                    onDragStart={(event: DragEvent<HTMLTableRowElement>) => {
                      if (locked) return;
                      event.dataTransfer.effectAllowed = 'move';
                      event.dataTransfer.setData('text/plain', p.id);
                      setDragId(p.id);
                      setDragOverId(null);
                    }}
                    onDragOver={(event) => {
                      if (!dragId || locked) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = 'move';
                      setDragOverId(p.id);
                    }}
                    onDragLeave={() => {
                      if (dragOverId === p.id) setDragOverId(null);
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (dragId) reorderByDrop(dragId, p.id);
                      setDragId(null);
                      setDragOverId(null);
                    }}
                    onDragEnd={() => {
                      setDragId(null);
                      setDragOverId(null);
                    }}
                  >
                    <td className="renumber-order-cell">
                      <span className={locked ? 'renumber-lock' : 'renumber-drag-handle'} title={locked ? 'Cover and Sheet Index stay first' : 'Drag to reorder'}>
                        {locked ? 'LOCK' : '⋮⋮'} {index + 1}
                      </span>
                    </td>
                    <td>{p.displaySheetCode || p.sheetCode || '—'}</td>
                    <td className="new-code">{p.include ? (next || '—') : '—'}</td>
                    <td>{p.sheetTitle}{p.continuationOf ? ' — CONTINUED' : ''}</td>
                    <td className="fam-cell">{fam.label}</td>
                    <td>{p.include ? 'Yes' : 'No'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={apply}>Apply order &amp; codes</button>
        </div>
      </div>
    </div>
  );
}
