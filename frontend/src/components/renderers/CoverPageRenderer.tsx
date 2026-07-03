import type { PageBlock, ProjectModel } from '../../model/types';

interface Props {
  block: PageBlock;
  project: ProjectModel;
}

/** Cover page: project identity from metadata + preserved source lines. */
export default function CoverPageRenderer({ block, project }: Props) {
  const lines = (block.rows ?? []).map((r) => r[0]).filter((t) => t && t.trim());
  const m = project.metadata;
  return (
    <div className="np-cover">
      <div className="np-cover-brand">
        <img src="/static/LOGO-750px.png" alt="Singh360" className="np-cover-logo" />
        <div className="np-cover-firm">SINGH360 INC.</div>
      </div>
      <div className="np-cover-title">{m.projectName || block.text || 'Project Cover'}</div>
      {m.location ? <div className="np-cover-sub">{m.location}</div> : null}
      <div className="np-cover-lines">
        {lines.map((ln, i) => (
          <div key={i} className="np-cover-line">{ln}</div>
        ))}
      </div>
    </div>
  );
}
