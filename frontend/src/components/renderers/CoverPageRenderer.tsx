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
  const title = meaningful(metadata.projectName)
    ? metadata.projectName.trim()
    : meaningful(block.text)
      ? block.text.trim()
      : 'Project Cover';
  const location = meaningful(metadata.location) ? metadata.location.trim() : '';

  const seen = new Set<string>();
  if (title) seen.add(title.toLowerCase());
  if (location) seen.add(location.toLowerCase());

  const lines = (block.rows ?? [])
    .map((row) => String(row[0] ?? '').trim())
    .filter((text) => meaningful(text))
    .filter((text) => {
      const key = text.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

  return (
    <div className="np-cover">
      <div className="np-cover-brand">
        <img src="/static/LOGO-750px.png" alt="Singh360" className="np-cover-logo" />
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
