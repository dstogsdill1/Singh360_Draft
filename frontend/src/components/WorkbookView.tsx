import type { Worksheet } from '../model/types';

interface Props {
  worksheets: Worksheet[];
  selectedWorksheetId?: string;
  onSelectWorksheet: (id: string) => void;
}

export default function WorkbookView({ worksheets, selectedWorksheetId, onSelectWorksheet }: Props) {
  return (
    <>
      {worksheets.map((ws) => (
        <button
          key={ws.id}
          className={`source-tab-btn ${ws.id === selectedWorksheetId ? 'active' : ''}`}
          onClick={() => onSelectWorksheet(ws.id)}
        >
          {ws.name}
        </button>
      ))}
    </>
  );
}
