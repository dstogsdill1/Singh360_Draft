import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { ProjectModel, SpreadsheetRegion } from '../model/types';
import {
  regionScale,
  spreadsheetPreflight,
  spreadsheetRegionBlock,
} from '../model/spreadsheetRegion';
import ExcelRangeRenderer from './renderers/ExcelRangeRenderer';
import '../styles/spreadsheetPageLayout.css';

interface Props {
  pageId: string;
  regions: SpreadsheetRegion[];
  project: ProjectModel;
  readOnly?: boolean;
  exporting?: boolean;
  onChange?: (regions: SpreadsheetRegion[]) => void;
}

type PointerAction = {
  id: string;
  mode: 'move' | 'resize';
  startX: number;
  startY: number;
  region: SpreadsheetRegion;
};

export default function SpreadsheetPageCanvas({
  pageId,
  regions,
  project,
  readOnly = false,
  exporting = false,
  onChange,
}: Props) {
  const action = useRef<PointerAction | null>(null);
  const draftRef = useRef<SpreadsheetRegion[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dragRegions, setDragRegions] = useState<SpreadsheetRegion[] | null>(null);
  const worksheetById = useMemo(
    () => new Map(project.worksheets.map((worksheet) => [worksheet.id, worksheet])),
    [project.worksheets],
  );
  const warnings = useMemo(
    () => spreadsheetPreflight(pageId, regions, project.worksheets),
    [pageId, project.worksheets, regions],
  );

  const updatePointer = (clientX: number, clientY: number) => {
    const current = action.current;
    if (!current || !onChange) return;
    const dx = clientX - current.startX;
    const dy = clientY - current.startY;
    const patch = current.mode === 'move'
      ? { x: Math.max(0, Math.min(1632 - current.region.width, current.region.x + dx)), y: Math.max(0, Math.min(912 - current.region.height, current.region.y + dy)) }
      : { width: Math.max(80, Math.min(1632 - current.region.x, current.region.width + dx)), height: Math.max(48, Math.min(912 - current.region.y, current.region.height + dy)) };
    const next = regions.map((region) => region.id === current.id ? { ...region, ...patch } : region);
    draftRef.current = next;
    setDragRegions(next);
  };
  const finishPointer = () => {
    const draft = draftRef.current;
    action.current = null;
    draftRef.current = null;
    setDragRegions(null);
    if (draft) onChange?.(draft);
  };
  const beginPointer = (
    event: ReactPointerEvent<HTMLButtonElement>,
    region: SpreadsheetRegion,
    mode: PointerAction['mode'],
  ) => {
    event.preventDefault();
    setSelectedId(region.id);
    action.current = { id: region.id, mode, startX: event.clientX, startY: event.clientY, region };
    const move = (pointerEvent: PointerEvent) => updatePointer(pointerEvent.clientX, pointerEvent.clientY);
    const finish = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      finishPointer();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
  };
  const displayRegions = dragRegions || regions;

  return <div
    className="spreadsheet-page-canvas"
    data-testid="spreadsheet-page-canvas"
    data-page-id={pageId}
  >
    {!exporting && warnings.length > 0 && <aside className="spreadsheet-preflight" aria-label="Spreadsheet preflight warnings">
      {warnings.map((warning, index) => <div key={`${warning.code}-${warning.regionId || 'page'}-${index}`} data-warning={warning.code}>{warning.message}</div>)}
    </aside>}
    {displayRegions.map((region) => {
      const worksheet = worksheetById.get(region.sourceSheetId);
      const block = worksheet ? spreadsheetRegionBlock(worksheet, region) : null;
      if (!worksheet || !block) return <div key={region.id} className="spreadsheet-region missing">Missing source: {region.range}</div>;
      const scale = regionScale(region, block);
      return <section
        key={region.id}
        className={`spreadsheet-region ${selectedId === region.id ? 'selected' : ''} overflow-${region.overflowMode}`}
        data-region-id={region.id}
        data-source-sheet={region.sourceSheetId}
        data-source-range={region.range}
        data-fit-mode={region.fitMode}
        data-scale={scale.toFixed(6)}
        style={{ left: region.x, top: region.y, width: region.width, height: region.height }}
        onClick={(event) => { event.stopPropagation(); if (!readOnly) setSelectedId(region.id); }}
      >
        {!readOnly && <button
          type="button"
          className="spreadsheet-region-handle"
          aria-label={`Move ${worksheet.name} ${region.range}`}
          onPointerDown={(event) => beginPointer(event, region, 'move')}
        >{worksheet.name}!{region.range}</button>}
        <div className="spreadsheet-region-content">
          <ExcelRangeRenderer block={block} scaleOverride={scale} embedded exporting={exporting} />
        </div>
        {!readOnly && <button
          type="button"
          className="spreadsheet-region-resize"
          aria-label={`Resize ${worksheet.name} ${region.range}`}
          onPointerDown={(event) => beginPointer(event, region, 'resize')}
        />}
      </section>;
    })}
  </div>;
}
