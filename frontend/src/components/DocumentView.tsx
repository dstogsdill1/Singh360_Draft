import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import PageRenderer from './PageRenderer';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';

interface Props {
  project: ProjectModel;
  activePage: PageModel;
  worksheets: Worksheet[];
  onGridChange: (worksheetId: string, grid: string[][]) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

export default function DocumentView({ project, activePage, worksheets, onGridChange, onCanvasChange }: Props) {
  const worksheet = worksheets.find((w) => w.id === activePage.linkedWorksheetId);

  return (
    <SheetFrame titleBlock={<TitleBlock project={project} page={activePage} />}>
      <PageRenderer
        page={activePage}
        worksheet={worksheet}
        project={project}
        onGridChange={onGridChange}
        onCanvasChange={onCanvasChange}
      />
    </SheetFrame>
  );
}
