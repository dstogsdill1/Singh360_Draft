import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  titleBlock: ReactNode;
  sourceView?: boolean;
}

export default function SheetFrame({ children, titleBlock, sourceView }: Props) {
  return (
    <div className="sheet-shell">
      <div className="sheet-inner">
        <div className={`sheet-body${sourceView ? ' sheet-body-source' : ''}`}>{children}</div>
        {titleBlock}
      </div>
    </div>
  );
}
