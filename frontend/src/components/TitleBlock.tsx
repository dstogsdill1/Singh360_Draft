import type { PageModel, ProjectModel } from '../model/types';

interface Props {
  project: ProjectModel;
  page: PageModel;
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div className="tb-field">
      <span className="tb-field-label">{label}</span>
      <span className="tb-field-value">{value || ''}</span>
    </div>
  );
}

export default function TitleBlock({ project, page }: Props) {
  const m = project.metadata;
  const pageLabel = page.pageNumber
    ? `Page ${page.pageNumber} of ${page.pageTotal ?? 0}`
    : `Page — of ${page.pageTotal ?? 0}`;

  return (
    <div className="sheet-title-block">
      {/* Firm / logo block */}
      <div className="tb-cell tb-firm">
        <img src="/static/LOGO-750px.png" alt="Singh360" className="tb-logo" />
        <div className="tb-firm-name">SINGH360 INC.</div>
        <div className="tb-firm-meta">Engineering Services</div>
        <div className="tb-firm-meta">singh360.com</div>
      </div>

      {/* Project metadata block */}
      <div className="tb-cell tb-stack">
        <Field label="Project" value={m.projectName} />
        <Field label="Location" value={m.location} />
        <Field label="File" value={m.sourceFile} />
      </div>

      {/* Sheet title + notes */}
      <div className="tb-cell tb-titleblock">
        <div className="tb-sheet-title">{page.sheetTitle || ''}</div>
        <div className="tb-notes">
          <span className="tb-field-label">Notes</span>
          <span className="tb-notes-value">{page.notes || ''}</span>
        </div>
      </div>

      {/* Revision / creator / date block */}
      <div className="tb-cell tb-stack">
        <Field label="Creator" value={m.createdBy} />
        <Field label="Created" value={m.createdDate} />
        <Field label="Edited By" value={m.editedBy} />
        <Field label="Version" value={m.version} />
        <Field label="Date" value={m.date} />
      </div>

      {/* Sheet code / page number block */}
      <div className="tb-cell tb-code">
        <span className="tb-field-label">Sheet</span>
        <span className="tb-code-value">{page.sheetCode || ''}</span>
        <span className="tb-page-label">{pageLabel}</span>
      </div>
    </div>
  );
}
