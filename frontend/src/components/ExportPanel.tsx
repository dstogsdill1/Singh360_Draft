interface Props {
  onExportPdf: () => Promise<void>;
}

export default function ExportPanel({ onExportPdf }: Props) {
  return (
    <div className="toolbar-inline">
      <button onClick={() => void onExportPdf()}>Export PDF (17x11)</button>
    </div>
  );
}
