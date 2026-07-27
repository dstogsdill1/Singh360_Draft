import type { PageModel, ProjectModel } from '../model/types';
import { formatDateOnly } from '../model/dateDisplay';

interface Props {
  project: ProjectModel;
  page: PageModel;
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div className="tb-field">
      <span className="tb-field-label">{label}</span>
      <span className="tb-field-value">{value || '—'}</span>
    </div>
  );
}

export default function TitleBlock({ project, page }: Props) {
  const m = project.metadata;
  const isContinuation = !!page.continuationOf || !!page.generatedContinuation;
  const cleanTitle = (page.sheetTitle || 'Untitled Sheet').replace(/\s*[—-]\s*CONTINUED\s*$/i, '').trim();
  const pageLabel = page.pageNumber
    ? `Sheet ${page.pageNumber} of ${page.pageTotal ?? 0}`
    : `Sheet — of ${page.pageTotal ?? 0}`;
  const projectName = m.projectName || project.projectDisplayName;
  const created = formatDateOnly(m.createdDate);
  const issued = formatDateOnly(m.issueDate || m.date);

  return (
    <div className="sheet-title-block tb-v3">
      <div className="tb-cell tb-firm">
        <img src="/static/LOGO-750px.png" alt="Singh360 Draft" className="tb-logo" />
        <div className="tb-firm-name">SINGH360 INC.</div>
        <div className="tb-firm-meta">Engineering Services · singh360.com</div>
      </div>

      <div className="tb-cell tb-stack">
        <Field label="Project" value={projectName} />
        <Field label="Location" value={m.location} />
      </div>

      <div className="tb-cell tb-titleblock">
        <div className="tb-sheet-title-row">
          <span className="tb-sheet-title">{cleanTitle}</span>
          {isContinuation && <span className="tb-continued">— CONTINUED</span>}
        </div>
        <div className="tb-notes">
          <span className="tb-field-label">Notes</span>
          <span className="tb-notes-value">{page.notes || '—'}</span>
        </div>
      </div>

      <div className="tb-cell tb-stack tb-rev">
        <Field label="Drawn By" value={m.drawnBy || m.createdBy} />
        <Field label="Checked By" value={m.checkedBy || m.editedBy} />
        <Field label="Created" value={created} />
        <div className="tb-field-pair">
          <Field label="Rev" value={m.revision} />
          <Field label="Issued" value={issued} />
        </div>
      </div>

      <div className="tb-cell tb-code">
        <span className="tb-field-label">Sheet No.</span>
        <span className="tb-code-value">{page.displaySheetCode || page.sheetCode || '—'}</span>
        <span className="tb-page-label">{pageLabel}</span>
      </div>
    </div>
  );
}
