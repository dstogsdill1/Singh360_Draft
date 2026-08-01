import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react';

interface Props {
  onClose: () => void;
}

interface NewProjectResponse {
  id?: string;
  project?: { id?: string; metadata?: Record<string, unknown> } & Record<string, unknown>;
  error?: string;
  detail?: string;
}

interface ProjectFields {
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
}

const fieldGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
  gap: 14,
  padding: 20,
};

const fieldStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  fontWeight: 700,
};

const inputStyle: CSSProperties = {
  minWidth: 0,
  border: '1px solid #aeb9c2',
  borderRadius: 5,
  padding: '9px 10px',
  fontWeight: 400,
};

const initialFields = (): ProjectFields => ({
  projectName: '',
  client: '',
  storeNumber: '',
  location: '',
  projectType: '',
  drawingSetTitle: '',
  preparedBy: '',
  checkedBy: '',
  createdDate: '',
  revision: '',
  notes: '',
  drawingPackageFileName: '',
});

export default function NewProjectWizard({ onClose }: Props) {
  const [fields, setFields] = useState<ProjectFields>(initialFields);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [customerLogo, setCustomerLogo] = useState<File | null>(null);
  const projectNameRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    projectNameRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose, submitting]);

  const setField = (name: keyof ProjectFields, value: string) => {
    setFields((current) => ({ ...current, [name]: value }));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const importFilesNow = submitter?.value === 'import';
    const projectName = fields.projectName.trim();
    if (!projectName) {
      setError('Project Name is required.');
      projectNameRef.current?.focus();
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const projectMetadata = {
        projectName,
        client: fields.client.trim(),
        storeNumber: fields.storeNumber.trim(),
        location: fields.location.trim(),
        projectType: fields.projectType.trim(),
        drawingSetTitle: fields.drawingSetTitle.trim(),
        preparedBy: fields.preparedBy.trim(),
        checkedBy: fields.checkedBy.trim(),
        createdDate: fields.createdDate,
        revision: fields.revision.trim(),
        notes: fields.notes.trim(),
        drawingPackageFileName: fields.drawingPackageFileName.trim(),
      };
      let body: BodyInit;
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (customerLogo) {
        const multipart = new FormData();
        multipart.append('metadata', JSON.stringify(projectMetadata));
        multipart.append('customerLogo', customerLogo);
        body = multipart;
      } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(projectMetadata);
      }
      const response = await fetch('/api/projects/new', {
        method: 'POST',
        headers,
        body,
      });
      let result: NewProjectResponse = {};
      try {
        result = await response.json() as NewProjectResponse;
      } catch {
        result = {};
      }
      if (!response.ok) {
        throw new Error(result.detail || result.error || response.statusText || 'Project creation failed.');
      }
      const projectId = String(result.id || result.project?.id || '').trim();
      if (!projectId) throw new Error('The server created no project ID.');
      window.location.assign(`/app?project=${encodeURIComponent(projectId)}&mode=editor${importFilesNow ? '&tool=add-import' : ''}`);
    } catch (requestError) {
      setError(String(requestError));
      setSubmitting(false);
    }
  };

  return (
    <div className="dashboard-overlay">
      <section
        className="dashboard-overlay-panel"
        style={{ height: 'auto', maxHeight: '96vh', overflow: 'auto' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
        aria-describedby="new-project-description"
      >
        <header className="overlay-head">
          <div>
            <div className="project-home-brand">NEW DRAWING PROJECT</div>
            <h2 id="new-project-title">Create a standalone drawing set</h2>
            <p id="new-project-description">Only Project Name is required. Everything else can be updated later.</p>
          </div>
          <button type="button" onClick={onClose} disabled={submitting} aria-label="Close New Drawing Project">
            Close
          </button>
        </header>

        <form onSubmit={submit}>
          <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0 }}>
            <div style={fieldGrid}>
              <label style={fieldStyle} htmlFor="new-project-name">
                Project Name <span aria-hidden="true">*</span>
                <input
                  ref={projectNameRef}
                  id="new-project-name"
                  name="projectName"
                  value={fields.projectName}
                  onChange={(event) => setField('projectName', event.target.value)}
                  autoComplete="organization"
                  required
                  aria-required="true"
                  style={inputStyle}
                />
              </label>
              <label style={fieldStyle} htmlFor="new-project-client">
                Customer / Client
                <input id="new-project-client" name="client" value={fields.client} onChange={(event) => setField('client', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-number">
                Store / Project Number
                <input id="new-project-number" name="storeNumber" value={fields.storeNumber} onChange={(event) => setField('storeNumber', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-location">
                Project Location
                <input id="new-project-location" name="location" value={fields.location} onChange={(event) => setField('location', event.target.value)} autoComplete="street-address" style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-type">
                Project Type
                <input id="new-project-type" name="projectType" value={fields.projectType} onChange={(event) => setField('projectType', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-drawing-set-title">
                Drawing Set Title
                <input id="new-drawing-set-title" name="drawingSetTitle" value={fields.drawingSetTitle} onChange={(event) => setField('drawingSetTitle', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-prepared-by">
                Prepared By
                <input id="new-project-prepared-by" name="preparedBy" value={fields.preparedBy} onChange={(event) => setField('preparedBy', event.target.value)} autoComplete="name" style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-checked-by">
                Checked By
                <input id="new-project-checked-by" name="checkedBy" value={fields.checkedBy} onChange={(event) => setField('checkedBy', event.target.value)} autoComplete="name" style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-created-date">
                Created Date
                <input id="new-project-created-date" name="createdDate" type="date" value={fields.createdDate} onChange={(event) => setField('createdDate', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle} htmlFor="new-project-revision">
                Revision
                <input id="new-project-revision" name="revision" value={fields.revision} onChange={(event) => setField('revision', event.target.value)} style={inputStyle} />
              </label>
              <label style={{ ...fieldStyle, gridColumn: '1 / -1' }} htmlFor="new-project-package-name">
                Drawing-package File Name
                <input id="new-project-package-name" name="drawingPackageFileName" value={fields.drawingPackageFileName} onChange={(event) => setField('drawingPackageFileName', event.target.value)} style={inputStyle} />
              </label>
              <label style={{ ...fieldStyle, gridColumn: '1 / -1' }} htmlFor="new-project-notes">
                Notes
                <textarea
                  id="new-project-notes"
                  name="notes"
                  value={fields.notes}
                  onChange={(event) => setField('notes', event.target.value)}
                  rows={4}
                  style={{ ...inputStyle, resize: 'vertical' }}
                />
              </label>
              <label style={{ ...fieldStyle, gridColumn: '1 / -1' }} htmlFor="new-project-customer-logo">
                Customer Logo
                <input
                  id="new-project-customer-logo"
                  name="customerLogo"
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  onChange={(event) => setCustomerLogo(event.target.files?.[0] || null)}
                  style={inputStyle}
                />
              </label>
            </div>
          </fieldset>

          {error ? <p className="dashboard-message error" role="alert">{error}</p> : null}
          <div className="welcome-actions" style={{ justifyContent: 'flex-start', padding: '0 20px 20px' }}>
            <button className="primary large" type="submit" name="nextStep" value="editor" disabled={submitting}>
              {submitting ? 'Creating Drawing Set…' : 'Create Blank Drawing Set'}
            </button>
            <button type="submit" name="nextStep" value="import" disabled={submitting}>Import Files Now</button>
            <button type="submit" name="nextStep" value="editor" disabled={submitting}>Skip and Open Editor</button>
            <button type="button" onClick={onClose} disabled={submitting}>Cancel</button>
          </div>
          {submitting ? <p className="muted" role="status">Creating the cover, sheet index, and project package…</p> : null}
        </form>
      </section>
    </div>
  );
}
