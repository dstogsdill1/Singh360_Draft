import type { PageBlock, ProjectModel } from '../../model/types';

interface Props {
  block: PageBlock;
  project: ProjectModel;
}

function valueFor(rows: string[][], keys: string[]): string {
  const lower = keys.map((k) => k.toLowerCase());
  for (const row of rows) {
    const cells = row.map((c) => String(c || '').trim()).filter(Boolean);
    const blob = cells.join(' ').toLowerCase();
    if (lower.some((k) => blob.includes(k))) {
      if (cells.length >= 2) return cells.slice(1).join(' ');
      return cells.join(' ');
    }
  }
  return '';
}

/** Centered Singh360 company/reference page. Source rows supply data only. */
export default function CompanyInfoRenderer({ block, project }: Props) {
  const rows = block.rows ?? [];
  const website = valueFor(rows, ['website', 'web', 'www']) || 'www.singh360.com';
  const phone = valueFor(rows, ['phone', 'tel']) || '';
  const address = valueFor(rows, ['address', 'location']) || project.metadata.location || '';
  const note =
    valueFor(rows, ['standard', 'note']) ||
    'Drawing package prepared to Singh360 EMS / MEP-R documentation standards.';

  return (
    <div className="np-company-info">
      <img src="/static/LOGO-750px.png" alt="Singh360 Draft" className="np-company-logo" />
      <div className="np-company-name">Singh360 Inc.</div>
      <div className="np-company-service">Engineering Services</div>
      <div className="np-company-details">
        {website && <div>{website}</div>}
        {phone && <div>{phone}</div>}
        {address && <div>{address}</div>}
      </div>
      <div className="np-company-note">{note}</div>
    </div>
  );
}
