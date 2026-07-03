import { useState } from 'react';
import type { PageBlock } from '../../model/types';

interface Props {
  block: PageBlock;
}

/** Renders an embedded/attached image, or a clean placeholder if not attached. */
export default function ImagePlaceholderRenderer({ block }: Props) {
  const [broken, setBroken] = useState(false);

  if (block.url && !broken) {
    return (
      <div className="np-image-embed">
        <img
          src={block.url}
          alt={block.filename || block.text || 'embedded image'}
          className="np-image-embed-img"
          onError={() => setBroken(true)}
        />
      </div>
    );
  }

  return (
    <div className="np-image-ph">
      <div className="np-image-ph-icon">▨</div>
      <div className="np-image-ph-text">
        {broken
          ? `Image failed to load: ${block.filename || block.text}`
          : `Image/underlay not attached: ${block.filename || block.text}`}
      </div>
      <button className="btn" disabled title="Asset attachment arrives in a later milestone">Attach Asset</button>
    </div>
  );
}
