interface Props {
  onExportPdf: () => Promise<void>;
}

export default function ExportPanel({ onExportPdf }: Props) {
  return (
    <button className="btn btn-primary" onClick={() => void onExportPdf()}>Export PDF (17x11)</button>
  );
}
