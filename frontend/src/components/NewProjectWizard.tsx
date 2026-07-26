import { useEffect, useMemo, useState } from 'react';
import { createTemplateProject, listProjectProfiles, listWorkbookTemplates, type ProjectProfile, type WorkbookTemplateRecord } from '../api/client';

const fields = [
  ['projectName', 'Project name', true], ['storeNumber', 'Store / site number', false],
  ['client', 'Client', false], ['location', 'Location', false], ['address', 'Address', false],
  ['subtype', 'Subtype', false], ['purpose', 'Purpose', false], ['scopeSummary', 'Scope summary', false],
  ['drawingPrefix', 'Drawing prefix', false], ['revision', 'Revision', false],
  ['drawnBy', 'Drawn by', false], ['checkedBy', 'Checked by', false],
  ['backupFolder', 'Optional synchronized backup folder', false],
] as const;

export default function NewProjectWizard() {
  const [profiles, setProfiles] = useState<ProjectProfile[]>([]);
  const [templates, setTemplates] = useState<WorkbookTemplateRecord[]>([]);
  const [profileId, setProfileId] = useState('EMS_FULL');
  const [templateId, setTemplateId] = useState('');
  const [metadata, setMetadata] = useState<Record<string, string>>({});
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([listProjectProfiles(), listWorkbookTemplates()]).then(([nextProfiles, nextTemplates]) => {
      setProfiles(nextProfiles);
      setTemplates(nextTemplates.filter((item) => item.active));
      setTemplateId(nextTemplates.find((item) => item.active)?.templateId || '');
    }).catch((reason) => setError(String(reason)));
  }, []);
  const profile = useMemo(() => profiles.find((item) => item.id === profileId), [profiles, profileId]);
  const template = useMemo(() => templates.find((item) => item.templateId === templateId), [templates, templateId]);
  const titles = ['Project Profile', 'Project Metadata', 'Workbook Template', 'Source Setup', 'Review and Create'];

  const create = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await createTemplateProject({ profileId, templateId, metadata: { ...metadata, projectType: profileId } });
      window.location.assign(`/app?project=${result.id}&view=sources`);
    } catch (reason) {
      setError(String(reason));
      setBusy(false);
    }
  };

  return (
    <div className="platform-shell">
      <header className="platform-header"><button onClick={() => window.location.assign('/app')}>Back</button><div><h1>New Project</h1><p>{titles[step]}</p></div></header>
      <nav className="wizard-steps" aria-label="Wizard progress">{titles.map((title, index) => <button key={title} className={index === step ? 'active' : ''} onClick={() => index < step && setStep(index)}>{index + 1}<span>{title}</span></button>)}</nav>
      <main className="wizard-body">
        {step === 0 && <div className="profile-grid">{profiles.filter((item) => item.id !== 'BASE_CORE').map((item) => <button key={item.id} className={profileId === item.id ? 'selected' : ''} onClick={() => setProfileId(item.id)}><strong>{item.displayName}</strong><span>{item.description}</span><small>{item.defaultIncludedFamilies.length} starting page families</small></button>)}</div>}
        {step === 1 && <div className="metadata-form">{fields.map(([key, label, required]) => <label key={key}><span>{label}{required ? ' *' : ''}</span>{key === 'scopeSummary' ? <textarea value={metadata[key] || ''} onChange={(event) => setMetadata({ ...metadata, [key]: event.target.value })} /> : <input required={required} value={metadata[key] || ''} onChange={(event) => setMetadata({ ...metadata, [key]: event.target.value })} />}</label>)}</div>}
        {step === 2 && <div className="template-list">{templates.map((item) => <button key={item.templateId} className={templateId === item.templateId ? 'selected' : ''} disabled={!item.supportedProfiles.includes(profileId)} onClick={() => setTemplateId(item.templateId)}><strong>{item.displayName}</strong><span>Version {item.version}</span><code>{item.sha256.slice(0, 16)}…</code></button>)}{!templates.length && <div className="platform-empty">No active runtime workbook template is registered. An administrator must validate and register the staged base template.</div>}</div>}
        {step === 3 && <div className="source-setup"><h2>Source folders will be created with the project</h2><div>{profile?.dataSheets.map((sheet) => <span key={sheet}>{sheet}</span>)}</div><p>Original uploads remain in the project Source Library. Files can be organized and archived after creation.</p></div>}
        {step === 4 && <div className="review-grid"><div><span>Project</span><strong>{metadata.projectName || 'Not entered'}</strong></div><div><span>Profile</span><strong>{profile?.displayName}</strong></div><div><span>Template</span><strong>{template?.displayName || 'Not selected'}</strong></div><div><span>Starting worksheets</span><strong>{profile?.dataSheets.length || 0}</strong></div><div><span>Starting page families</span><strong>{profile?.defaultIncludedFamilies.length || 0}</strong></div></div>}
        {error && <div className="platform-error">{error}</div>}
      </main>
      <footer className="wizard-footer"><button disabled={step === 0 || busy} onClick={() => setStep(step - 1)}>Previous</button>{step < 4 ? <button className="primary" disabled={step === 1 && !metadata.projectName?.trim() || step === 2 && !templateId} onClick={() => setStep(step + 1)}>Continue</button> : <button className="primary" disabled={busy || !templateId || !metadata.projectName?.trim()} onClick={() => void create()}>{busy ? 'Creating…' : 'Create Project'}</button>}</footer>
    </div>
  );
}
