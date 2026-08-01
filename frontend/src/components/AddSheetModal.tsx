import { useState } from 'react';

interface Props {
  suggestedCode?: string;
  onAdd: (title: string, code: string, template: string) => void;
  onCancel: () => void;
}

const TEMPLATES = [
  { value: 'data-grid', label: 'Table / Schedule' },
  { value: 'canvas', label: 'Image / Layout' },
  { value: 'matrix', label: 'Matrix' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'underlay', label: 'Underlay / Reference' },
];

export default function AddSheetModal({ suggestedCode = '', onAdd, onCancel }: Props) {
  const [title, setTitle] = useState('');
  const [code, setCode] = useState(suggestedCode);
  const [template, setTemplate] = useState('data-grid');

  const submit = () => {
    const t = title.trim() || 'New Sheet';
    onAdd(t, code.trim(), template);
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Add Blank Sheet</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>
        <div className="modal-body">
          <div className="field">
            <label htmlFor="as-title">Sheet Title</label>
            <input
              id="as-title"
              type="text"
              value={title}
              placeholder="New Sheet"
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
            />
          </div>
          <div className="field">
            <label htmlFor="as-code">Sheet Code (optional — set after Renumber)</label>
            <input
              id="as-code"
              type="text"
              value={code}
              placeholder="Leave blank to assign after renumber"
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="as-template">Page Template</label>
            <select id="as-template" value={template} onChange={(e) => setTemplate(e.target.value)}>
              {TEMPLATES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={submit}>Add Sheet</button>
        </div>
      </div>
    </div>
  );
}
