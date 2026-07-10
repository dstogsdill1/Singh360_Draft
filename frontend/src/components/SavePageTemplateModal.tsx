import { useState } from 'react';
import type { PageModel } from '../model/types';
import { savePageTemplate } from '../api/client';

interface Props {
  page: PageModel;
  thumbnailDataUrl?: string;
  onSaved: () => void;
  onCancel: () => void;
}

export default function SavePageTemplateModal({ page, thumbnailDataUrl, onSaved, onCancel }: Props) {
  const [name, setName] = useState(page.sheetTitle || 'Page Template');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const doSave = async () => {
    if (!name.trim()) return;
    setLoading(true);
    setError('');
    try {
      await savePageTemplate(page, name.trim(), thumbnailDataUrl);
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Save Page as Template</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>
        <div className="modal-body">
          <p className="cw-note">
            Saves canvas objects, blocks, and layout metadata from the active page.
            Sheet code and project links are not stored.
          </p>
          <div className="field">
            <label htmlFor="tpl-name">Template name</label>
            <input
              id="tpl-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          {error && <p className="modal-error">{error}</p>}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" disabled={loading || !name.trim()} onClick={() => void doSave()}>
            {loading ? 'Saving…' : 'Save Template'}
          </button>
        </div>
      </div>
    </div>
  );
}
