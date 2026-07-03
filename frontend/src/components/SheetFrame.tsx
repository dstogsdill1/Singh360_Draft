import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  titleBlock: ReactNode;
}

export default function SheetFrame({ children, titleBlock }: Props) {
  return (
    <div className="sheet-shell">
      <div className="sheet-inner">
        <div className="sheet-body">{children}</div>
        {titleBlock}
      </div>
    </div>
  );
}
