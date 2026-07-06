interface Props {
  pageCount: number;
  includedCount: number;
  worksheetCount: number;
  activeLabel: string;
  zoomPct: number;
  port?: string;
  drawingHint?: string;
}

export default function StatusBar({ pageCount, includedCount, worksheetCount, activeLabel, zoomPct, drawingHint }: Props) {
  return (
    <div className="status-bar">
      <span className="sb-item">Singh360 Draft</span>
      <span className="sb-item">Pages: {pageCount}</span>
      <span className="sb-item">Included: {includedCount}</span>
      <span className="sb-item">Source tabs: {worksheetCount}</span>
      <span className="sb-item">Active: {activeLabel}</span>
      {drawingHint ? <span className="sb-item sb-hint">{drawingHint}</span> : null}
      <span className="sb-item sb-right">Zoom: {zoomPct}%</span>
    </div>
  );
}
