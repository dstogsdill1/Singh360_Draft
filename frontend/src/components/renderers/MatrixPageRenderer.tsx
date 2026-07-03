import type { PageBlock } from '../../model/types';
import TablePageRenderer from './TablePageRenderer';

interface Props {
  block: PageBlock;
  onChange: (patch: Partial<PageBlock>) => void;
}

/** Responsibility-matrix style block: fixed left description columns + compact marks. */
export default function MatrixPageRenderer({ block, onChange }: Props) {
  return <TablePageRenderer block={block} onChange={onChange} variant="matrix" />;
}
