import type { PageBlock } from '../../model/types';

interface Props {
  block: PageBlock;
}

/** Clean placeholder for a referenced but not-yet-attached image/underlay asset. */
export default function ImagePlaceholderRenderer({ block }: Props) {
  return (
    <div className="np-image-ph">
      <div className="np-image-ph-icon">▨</div>
      <div className="np-image-ph-text">Image/underlay not attached: {block.filename || block.text}</div>
      <button className="btn" disabled title="Asset attachment arrives in a later milestone">Attach Asset</button>
    </div>
  );
}
