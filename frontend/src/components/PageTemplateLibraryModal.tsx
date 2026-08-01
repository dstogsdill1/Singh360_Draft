import { useEffect, useState } from 'react';
import {
  deletePageTemplate,
  getPageTemplatePayload,
  listPageTemplates,
  renamePageTemplate,
  type PageTemplateEntry,
} from '../api/client';
import type { PageModel } from '../model/types';
import { instantiatePageTemplate } from '../model/pageDuplication';

function newPageId() {
  return `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function findPreviewUrl(value: unknown): string {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findPreviewUrl(item);
      if (found) return found;
    }
    return '';
  }
  if (!value || typeof value !== 'object') return '';

  const record = value as Record<string, unknown>;
  for (const key of ['src', 'url', 'sourceUrl', 'symbolUrl']) {
    const candidate = record[key];
    if (
      typeof candidate === 'string'
      && (
        candidate.startsWith('data:image/')
        || candidate.startsWith('/api/')
        || candidate.startsWith('http://')
        || candidate.startsWith('https://')
      )
    ) {
      return candidate;
    }
  }

  for (const item of Object.values(record)) {
    const found = findPreviewUrl(item);
    if (found) return found;
  }
  return '';
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
  const [previewUrl, setPreviewUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [inserting, setInserting] = useState(false);
  const [error, setError] = useState('');
  const [renameId, setRenameId] = useState('');
  const [renameValue, setRenameValue] = useState('');

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      const list = await listPageTemplates();
      setTemplates(list);
      setSelectedId((current) => (
        list.some((entry) => entry.id === current)
          ? current
          : list[0]?.id || ''
      ));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const selected = templates.find((template) => template.id === selectedId);

  useEffect(() => {
    let alive = true;
    setPreviewUrl(selected?.thumbnailUrl || '');

    if (!selectedId || selected?.thumbnailUrl) {
      return () => { alive = false; };
    }

    getPageTemplatePayload(selectedId)
      .then((payload) => {
        if (alive) setPreviewUrl(findPreviewUrl(payload));
      })
      .catch(() => {
        if (alive) setPreviewUrl('');
      });

    return () => { alive = false; };
  }, [selectedId, selected?.thumbnailUrl]);

  const doInsert = async () => {
    if (!selectedId || !onInsert || inserting) return;
    setInserting(true);
    setError('');

    try {
      const payload = await getPageTemplatePayload(selectedId);
      const pageId = newPageId();
      const page = instantiatePageTemplate(
        payload as unknown as PageModel,
        pageId,
        selected?.name,
      );

      if (
        page.canvasObjects.length > 0
        && page.pageType !== 'hybrid'
        && page.pageType !== 'underlay'
      ) {
        page.pageType = 'canvas';
      }

      onInsert(page, insertMode);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setInserting(false);
    }
  };

  const doDelete = async (template: PageTemplateEntry) => {
    if (!window.confirm(`Delete template "${template.name}"?`)) return;
    setError('');
    try {
      await deletePageTemplate(template.id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const doRename = async () => {
    if (!renameId || !renameValue.trim()) return;
    setError('');
    try {
      await renamePageTemplate(renameId, renameValue.trim());
      setRenameId('');
      setRenameValue('');
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{manageOnly ? 'Manage Page Templates' : 'Insert Page Template'}</h2>
          <button className="modal-x" onClick={onClose} title="Close">×</button>
        </div>

        <div className="modal-body">
          <p className="cw-note">
            {templates.length} saved template{templates.length === 1 ? '' : 's'}.
            Duplicate names are automatically collapsed, and saving the same name updates it.
          </p>

          {loading && <p>Loading templates…</p>}
          {error && <p className="modal-error">{error}</p>}

          {!loading && templates.length === 0 && (
            <p className="cw-note">
              No saved page templates yet. Open a finished layout and use
              <strong> Save Page as Template</strong>.
            </p>
          )}

          {templates.length > 0 && (
            <div className="pt-lib-grid">
              <div className="pt-lib-list">
                {templates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    className={`pt-lib-item ${selectedId === template.id ? 'active' : ''}`}
                    onClick={() => setSelectedId(template.id)}
                    onDoubleClick={() => {
                      if (!manageOnly) void doInsert();
                    }}
                  >
                    <strong>{template.name}</strong>
                    <span>
                      {template.pageType}
                      {template.layoutProfile ? ` · ${template.layoutProfile}` : ''}
                    </span>
                  </button>
                ))}
              </div>

              <div className="pt-lib-preview">
                {previewUrl ? (
                  <img src={previewUrl} alt={selected?.name || 'Template preview'} />
                ) : (
                  <div className="pt-lib-no-thumb">
                    No preview image was stored for this older template.
                    Saving it again will create one.
                  </div>
                )}

                {selected && (
                  <div className="pt-lib-actions">
                    <button
                      className="btn"
                      type="button"
                      onClick={() => {
                        setRenameId(selected.id);
                        setRenameValue(selected.name);
                      }}
                    >
                      Rename
                    </button>
                    <button
                      className="btn"
                      type="button"
                      onClick={() => void doDelete(selected)}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {renameId && (
            <div className="field-row" style={{ marginTop: 12 }}>
              <input
                type="text"
                value={renameValue}
                autoFocus
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void doRename();
                }}
              />
              <button className="btn" type="button" onClick={() => void doRename()}>
                Save name
              </button>
              <button className="btn" type="button" onClick={() => setRenameId('')}>
                Cancel
              </button>
            </div>
          )}

          {!manageOnly && templates.length > 0 && (
            <div className="field" style={{ marginTop: 12 }}>
              <label>Insert mode</label>
              <select
                value={insertMode}
                onChange={(e) => setInsertMode(e.target.value as TemplateInsertMode)}
              >
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
            <button
              className="btn btn-primary"
              disabled={!selectedId || loading || inserting}
              onClick={() => void doInsert()}
            >
              {inserting ? 'Inserting page and images…' : 'Insert Template'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
