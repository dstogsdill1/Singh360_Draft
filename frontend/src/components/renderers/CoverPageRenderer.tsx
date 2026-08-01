import type { PageBlock, ProjectModel } from '../../model/types';

interface Props {
  block: PageBlock;
  project: ProjectModel;
}

const meaningful = (value: unknown): value is string => {
  const text = String(value ?? '').trim();
  return !!text && /[A-Za-z0-9]/.test(text);
};

export default function CoverPageRenderer({ block, project }: Props) {
  const metadata = project.metadata;
  const standaloneManagedCover = project.projectMode === 'standalone_layout';
  const title = meaningful(metadata.projectName)
    ? metadata.projectName.trim()
    : standaloneManagedCover && meaningful(project.projectDisplayName)
      ? String(project.projectDisplayName).trim()
      : meaningful(block.text)
      ? block.text.trim()
      : 'Project Cover';
  const location = meaningful(metadata.location) ? metadata.location.trim() : '';

  const seen = new Set<string>();
  if (title) seen.add(title.toLowerCase());
  if (location) seen.add(location.toLowerCase());

  // Migrated workbook cover rows remain in project provenance for rollback,
  // but Project Settings is the sole visible authority in standalone mode.
  const legacyLines = (standaloneManagedCover ? [] : (block.rows ?? []))
    .map((row) => String(row[0] ?? '').trim())
    .filter((text) => meaningful(text));
  const settingsLines = [
    metadata.drawingSetTitle,
    metadata.client ? `Client: ${metadata.client}` : '',
    metadata.storeNumber ? `Project No.: ${metadata.storeNumber}` : '',
    metadata.projectType ? `Project Type: ${metadata.projectType}` : '',
    metadata.revision ? `Revision: ${metadata.revision}` : '',
    metadata.createdDate ? `Created: ${metadata.createdDate.slice(0, 10)}` : '',
    metadata.preparedBy || metadata.drawnBy || metadata.createdBy
      ? `Prepared By: ${metadata.preparedBy || metadata.drawnBy || metadata.createdBy}`
      : '',
    metadata.checkedBy ? `Checked By: ${metadata.checkedBy}` : '',
    metadata.notes,
  ].map((value) => String(value ?? '').trim()).filter(meaningful);
  const lines = [...settingsLines, ...legacyLines].filter((line) => {
    const key = line.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const customerLogo = String(metadata.customerLogoAsset || '').trim();
  const customerLogoUrl = customerLogo
    ? (customerLogo.startsWith('/') ? customerLogo : `/api/assets/${project.id}/${customerLogo}`)
    : '';

  return (
    <div className="np-cover">
      <div className="np-cover-brand">
        <img src="/static/LOGO-750px.png" alt="Singh360 Draft" className="np-cover-logo" />
        {customerLogoUrl ? <img src={customerLogoUrl} alt="Customer logo" className="np-cover-customer-logo" /> : null}
        <div className="np-cover-firm">SINGH360 INC.</div>
      </div>
      <div className="np-cover-title">{title}</div>
      {location ? <div className="np-cover-sub">{location}</div> : null}
      <div className="np-cover-lines">
        {lines.map((line, index) => (
          <div key={`${index}-${line}`} className="np-cover-line">{line}</div>
        ))}
      </div>
    </div>
  );
}
