import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import CanvasEditor from './CanvasEditor';
import GridPage from './GridPage';

interface Props {
  page: PageModel;
  worksheet?: Worksheet;
  project: ProjectModel;
  onGridChange: (worksheetId: string, grid: string[][]) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

export default function PageRenderer({ page, worksheet, onGridChange, onCanvasChange }: Props) {
  if (page.pageType === 'canvas' || page.pageType === 'hybrid' || page.pageType === 'underlay') {
    return <CanvasEditor serialized={page.canvasObjects || []} onSerializedChange={(o) => onCanvasChange(page.id, o)} />;
  }

  return (
    <GridPage
      grid={worksheet?.grid || [[]]}
      onGridChange={(grid) => {
        if (!page.linkedWorksheetId) return;
        onGridChange(page.linkedWorksheetId, grid);
      }}
    />
  );
}
