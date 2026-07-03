import type { PageModel, ProjectModel } from '../model/types';

interface Props {
  project: ProjectModel;
  page: PageModel;
}

export default function TitleBlock({ project, page }: Props) {
  const pageLabel = page.pageNumber ? `Page ${page.pageNumber} of ${page.pageTotal ?? 0}` : `Page - of ${page.pageTotal ?? 0}`;
  return (
    <div className="sheet-title-block">
      <div className="tb-cell">
        <div className="tb-mini">SINGH360 INC.</div>
        <div className="tb-mini">Engineering Services</div>
        <img src="/static/LOGO-750px.png" alt="Singh360" className="logo-img" />
      </div>
      <div className="tb-cell">
        <div className="tb-mini">Project</div>
        <div>{project.metadata.projectName || ''}</div>
        <div className="tb-mini">Creator</div>
        <div>{project.metadata.createdBy || ''}</div>
      </div>
      <div className="tb-cell">
        <div className="tb-mini">Sheet Code</div>
        <div className="tb-title">{page.sheetCode || ''}</div>
        <div className="tb-mini">Sheet Title</div>
        <div>{page.sheetTitle || ''}</div>
      </div>
      <div className="tb-cell">
        <div className="tb-mini">Created</div>
        <div>{project.metadata.createdDate || ''}</div>
        <div className="tb-mini">Version</div>
        <div>{project.metadata.version || ''}</div>
        <div className="tb-mini tb-mini-spaced">{pageLabel}</div>
      </div>
    </div>
  );
}
