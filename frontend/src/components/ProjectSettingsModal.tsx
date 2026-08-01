import { useState } from 'react';
import type { ProjectModel } from '../model/types';

interface Props {
  project: ProjectModel;
  onSave: (update: ProjectSettingsUpdate) => Promise<boolean>;
  onCancel: () => void;
}

export interface ProjectSettingsUpdate {
  projectDisplayName: string;
  includeCover: boolean;
  metadata: Partial<ProjectModel['metadata']>;
}

type Settings = {
  projectName: string;
  client: string;
  storeNumber: string;
  location: string;
  projectType: string;
  drawingSetTitle: string;
  preparedBy: string;
  checkedBy: string;
  createdDate: string;
  revision: string;
  notes: string;
  drawingPackageFileName: string;
  includeCover: boolean;
};

type TextSettingKey = Exclude<keyof Settings, 'includeCover'>;

function initialSettings(project: ProjectModel): Settings {
  const metadata = project.metadata;
  return {
    projectName: metadata.projectName || project.projectDisplayName || '',
    client: metadata.client || '',
    storeNumber: metadata.storeNumber || '',
    location: metadata.location || '',
    projectType: metadata.projectType || '',
    drawingSetTitle: metadata.drawingSetTitle || '',
    preparedBy: metadata.preparedBy || metadata.drawnBy || metadata.createdBy || '',
    checkedBy: metadata.checkedBy || '',
    createdDate: metadata.createdDate?.slice(0, 10) || '',
    revision: metadata.revision || '',
    notes: metadata.notes || '',
    drawingPackageFileName: metadata.drawingPackageFileName || '',
    includeCover: project.coverSettings?.include !== false,
  };
}

export default function ProjectSettingsModal({ project, onSave, onCancel }: Props) {
  const [settings, setSettings] = useState<Settings>(() => initialSettings(project));
  const [customerLogo, setCustomerLogo] = useState<File | null>(null);
  const [removeCustomerLogo, setRemoveCustomerLogo] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const patch = <Key extends keyof Settings>(key: Key, value: Settings[Key]) => (
    setSettings((current) => ({ ...current, [key]: value }))
  );

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const projectName = settings.projectName.trim();
    if (!projectName) return;
    setSaving(true);
    setError('');
    try {
      const { includeCover, ...metadataSettings } = settings;
      let customerLogoAsset = removeCustomerLogo ? '' : (project.metadata.customerLogoAsset || '');
      if (customerLogo) {
        const body = new FormData();
        body.append('file', customerLogo);
        const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}/assets`, { method: 'POST', body });
        const result = await response.json() as { asset?: { url?: string }; detail?: string; error?: string };
        if (!response.ok || !result.asset?.url) {
          throw new Error(result.detail || result.error || 'Customer logo upload failed.');
        }
        customerLogoAsset = result.asset.url;
      }
      const saved = await onSave({
        projectDisplayName: projectName,
        includeCover,
        metadata: {
          ...metadataSettings,
          projectName,
          preparedBy: settings.preparedBy,
          createdBy: settings.preparedBy,
          drawnBy: settings.preparedBy,
          customerLogoAsset,
        },
      });
      if (!saved) throw new Error('Project Settings could not be confirmed on the server. Your drawing remains open and unchanged.');
    } catch (nextError) {
      setError(String(nextError));
      setSaving(false);
    }
  };

  const fields: Array<[TextSettingKey, string, boolean]> = [
    ['projectName', 'Project Name', true],
    ['client', 'Customer / Client', false],
    ['storeNumber', 'Store / Project Number', false],
    ['location', 'Project Location', false],
    ['projectType', 'Project Type', false],
    ['drawingSetTitle', 'Drawing Set Title', false],
    ['preparedBy', 'Prepared By', false],
    ['checkedBy', 'Checked By', false],
    ['createdDate', 'Created Date', false],
    ['revision', 'Revision', false],
    ['drawingPackageFileName', 'Drawing-package File Name', false],
  ];

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal modal-wide project-settings-modal" role="dialog" aria-modal="true" aria-labelledby="project-settings-title" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <h2 id="project-settings-title">Project Settings</h2>
            <p>Cover and title-block fields update from this standalone project.</p>
          </div>
          <button type="button" className="modal-x" aria-label="Close Project Settings" onClick={onCancel} disabled={saving}>×</button>
        </div>
        <div className="modal-body project-settings-grid">
          {fields.map(([key, label, required]) => (
            <label key={key}>
              <span>{label}{required ? ' *' : ''}</span>
              <input
                value={String(settings[key])}
                required={required}
                disabled={saving}
                type={key === 'createdDate' ? 'date' : 'text'}
                onChange={(event) => patch(key, event.target.value)}
              />
            </label>
          ))}
          <label className="project-settings-notes">
            <span>Notes</span>
            <textarea value={settings.notes} rows={4} disabled={saving} onChange={(event) => patch('notes', event.target.value)} />
          </label>
          <div className="project-settings-notes">
            <label htmlFor="project-customer-logo">Customer Logo</label>
            <input
              id="project-customer-logo"
              type="file"
              disabled={saving}
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={(event) => {
                const file = event.target.files?.[0] || null;
                setCustomerLogo(file);
                if (file) setRemoveCustomerLogo(false);
              }}
            />
            {project.metadata.customerLogoAsset ? <small>Current project-local customer logo is set.</small> : null}
            {project.metadata.customerLogoAsset ? (
              <label className="project-settings-check">
                <input
                  type="checkbox"
                  disabled={saving}
                  checked={removeCustomerLogo}
                  onChange={(event) => {
                    setRemoveCustomerLogo(event.target.checked);
                    if (event.target.checked) setCustomerLogo(null);
                  }}
                />
                Clear the current customer logo when settings are saved
              </label>
            ) : null}
          </div>
          <details className="project-settings-advanced">
            <summary>Advanced cover options</summary>
            <label className="project-settings-check">
              <input
                type="checkbox"
                disabled={saving}
                checked={settings.includeCover}
                onChange={(event) => patch('includeCover', event.target.checked)}
              />
              Include the automatic Cover in the exported drawing set
            </label>
            <small>The Cover stays recoverable in the editor when excluded.</small>
          </details>
          {error ? <p role="alert" className="import-error">{error}</p> : null}
        </div>
        <div className="modal-foot">
          <button type="button" onClick={onCancel} disabled={saving}>Cancel</button>
          <button type="submit" className="primary" disabled={saving}>{saving ? 'Saving Settings…' : 'Save Project Settings'}</button>
        </div>
      </form>
    </div>
  );
}
