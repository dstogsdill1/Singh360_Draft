import { useEffect, useState } from 'react';
import {
  deletePageTemplate,
  getPageTemplatePayload,
  listPageTemplates,
  renamePageTemplate,
  type PageTemplateEntry,
} from '../api/client';
import type { PageModel } from '../model/types';

function newPageId() {
  return `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export type TemplateInsertMode = 'new_after' | 'replace_canvas' | 'overlay';

interface Props {
  manageOnly?: boolean;
  onInsert?: (page: PageModel, mode: TemplateInsertMode) => void;
  onClose: () => void;
}

export default function PageTemplateLibraryModal({ manageOnly, onInsert, onClose }: Props) {
  const [templates, setTemplates] = useState<PageTemplateEntry[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [insertMode, setInsertMode] = useState<TemplateInsertMode>('new_after');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [renameId, setRenameId] = useState('');
  const [renameValue, setRenameValue] = useState('');

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      const list = await listPageTemplates();
      setTemplates(list);
      if (!selectedId && list.length) setSelectedId(list[0].id);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const selected = templates.find((t) => t.id === selectedId);

  const doInsert = async () => {
    if (!selectedId || !onInsert) return;
    setLoading(true);
    setError('');
    try {
      const payload = await getPageTemplatePayload(selectedId);
      const page = payload as unknown as PageModel;
      page.id = newPageId();
      page.sheetCode = 'NEW';
      page.displaySheetCode = 'NEW';
      page.sheetTitle = selected?.name || page.sheetTitle || 'From Template';
      page.canvasObjects = [...(page.canvasObjects || [])];
      page.blocks = [...(page.blocks || [])];
      onInsert(page, insertMode);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const doDelete = async (id: string) => {
    if (!window.confirm('Delete this page template?')) return;
    await deletePageTemplate(id);
    if (selectedId === id) setSelectedId('');
    await refresh();
  };

  const doRename = async () => {
    if (!renameId || !renameValue.trim()) return;
    await renamePageTemplate(renameId, renameValue.trim());
    setRenameId('');
    setRenameValue('');
    await refresh();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{manageOnly ? 'Manage Page Templates' : 'Insert Page Template'}</h2>
          <button className="modal-x" onClick={onClose} title="Close">×</button>
        </div>
        <div className="modal-body">
          {loading && <p>Loading templates…</p>}
          {error && <p className="modal-error">{error}</p>}
          {!loading && templates.length === 0 && (
            <p className="cw-note">No saved page templates yet. Use <strong>Save Page as Template</strong> on a finished layout page.</p>
          )}
          {templates.length > 0 && (
            <div className="pt-lib-grid">
              <div className="pt-lib-list">
                {templates.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`pt-lib-item ${selectedId === t.id ? 'active' : ''}`}
                    onClick={() => setSelectedId(t.id)}
                  >
                    <strong>{t.name}</strong>
                    <span>{t.pageType}{t.layoutProfile ? ` · ${t.layoutProfile}` : ''}</span>
                  </button>
                ))}
              </div>
              <div className="pt-lib-preview">
                {selected?.thumbnailUrl ? (
                  <img src={selected.thumbnailUrl} alt={selected.name} />
                ) : (
                  <div className="pt-lib-no-thumb">No thumbnail</div>
                )}
                {selected && (
                  <div className="pt-lib-actions">
                    <button className="btn" type="button" onClick={() => { setRenameId(selected.id); setRenameValue(selected.name); }}>
                      Rename
                    </button>
                    <button className="btn" type="button" onClick={() => void doDelete(selected.id)}>Delete</button>
                  </div>
                )}
              </div>
            </div>
          )}
          {renameId && (
            <div className="field-row" style={{ marginTop: 12 }}>
              <input type="text" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
              <button className="btn" type="button" onClick={() => void doRename()}>Save name</button>
              <button className="btn" type="button" onClick={() => setRenameId('')}>Cancel</button>
            </div>
          )}
          {!manageOnly && templates.length > 0 && (
            <div className="field" style={{ marginTop: 12 }}>
              <label>Insert mode</label>
              <select value={insertMode} onChange={(e) => setInsertMode(e.target.value as TemplateInsertMode)}>
                <option value="new_after">New page after current</option>
                <option value="replace_canvas">Replace current page canvas only</option>
                <option value="overlay">Overlay onto current page</option>
              </select>
            </div>
          )}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>Close</button>
          {!manageOnly && templates.length > 0 && (
            <button className="btn btn-primary" disabled={!selectedId || loading} onClick={() => void doInsert()}>
              Insert Template
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
