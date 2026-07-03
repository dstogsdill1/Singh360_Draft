import { useMemo, useState } from 'react';
import type { PageModel } from '../model/types';

interface Props {
  pages: PageModel[];
  onApply: (updated: PageModel[]) => void;
  onCancel: () => void;
}

type Scheme = 'keep' | 'sequential' | 'prefix';

const CONT_SUFFIX = ['', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

/**
 * Preview + apply engineering sheet codes. Sheet codes are user-controlled and
 * separate from the auto "Page X of Y" package order. Continuation pages inherit
 * their base page's code with a letter suffix (4.0 -> 4.0a, 4.0b).
 */
export default function RenumberModal({ pages, onApply, onCancel }: Props) {
  const [scheme, setScheme] = useState<Scheme>('sequential');
  const [prefix, setPrefix] = useState('');

  const included = useMemo(() => pages.filter((p) => p.include), [pages]);

  // Compute proposed codes keyed by page id.
  const proposed = useMemo(() => {
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
  }, [included, scheme, prefix]);

  const apply = () => {
    const updated = pages.map((p) => {
      const code = proposed.get(p.id);
      if (code === undefined) return p;
      return { ...p, sheetCode: code, displaySheetCode: code };
    });
    onApply(updated);
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Renumber Sheet Codes</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          <div className="renumber-options">
            <label className={scheme === 'keep' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'keep'} onChange={() => setScheme('keep')} />
              Keep existing sheet codes
            </label>
            <label className={scheme === 'sequential' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'sequential'} onChange={() => setScheme('sequential')} />
              Sequential decimal (1.0, 2.0, 3.0…)
            </label>
            <label className={scheme === 'prefix' ? 'active' : ''}>
              <input type="radio" name="scheme" checked={scheme === 'prefix'} onChange={() => setScheme('prefix')} />
              Prefix + sequential
              <input
                className="prefix-input"
                type="text"
                placeholder="EMS"
                value={prefix}
                disabled={scheme !== 'prefix'}
                onChange={(e) => setPrefix(e.target.value)}
              />
            </label>
            <p className="renumber-note">
              Continuation pages inherit the base code with a suffix (4.0 → 4.0a, 4.0b). “Page X of Y” updates automatically and is independent of sheet codes.
            </p>
          </div>

          <table className="renumber-preview">
            <thead>
              <tr>
                <th>Old Code</th>
                <th>New Code</th>
                <th>Sheet Title</th>
                <th>Included</th>
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => {
                const next = proposed.get(p.id) ?? p.sheetCode;
                const changed = p.include && next !== (p.sheetCode || '');
                return (
                  <tr key={p.id} className={changed ? 'changed' : ''}>
                    <td>{p.displaySheetCode || p.sheetCode || '—'}</td>
                    <td className="new-code">{p.include ? (next || '—') : '—'}</td>
                    <td>{p.sheetTitle}{p.continuationOf ? ' — CONTINUED' : ''}</td>
                    <td>{p.include ? 'Yes' : 'No'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={apply}>Apply</button>
        </div>
      </div>
    </div>
  );
}
