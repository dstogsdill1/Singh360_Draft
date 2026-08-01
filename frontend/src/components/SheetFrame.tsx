import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  titleBlock: ReactNode;
  sourceView?: boolean;
  fullSheet?: boolean;
  fullSheetPageLabel?: string;
}

export default function SheetFrame({ children, titleBlock, sourceView, fullSheet = false, fullSheetPageLabel = '' }: Props) {
  return (
    <div className={`sheet-shell${fullSheet ? ' sheet-shell-full' : ''}`}>
      <div className={`sheet-inner${fullSheet ? ' sheet-inner-full' : ''}`}>
        <div className={`sheet-body${sourceView ? ' sheet-body-source' : ''}${fullSheet ? ' sheet-body-full' : ''}`}>{children}</div>
        {fullSheet ? null : titleBlock}
        {fullSheet && fullSheetPageLabel ? <div className="full-sheet-page-label">{fullSheetPageLabel}</div> : null}
      </div>
    </div>
  );
}
