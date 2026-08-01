import { useEffect, useRef, useState } from 'react';
import type { PageModel } from '../model/types';
import { savePageTemplate } from '../api/client';
import { preparePageTemplatePayload } from '../model/pageDuplication';

interface Props {
  page: PageModel;
  thumbnailDataUrl?: string;
  onSaved: () => void;
  onCancel: () => void;
}

const IMAGE_KEYS = new Set(['src', 'url', 'sourceUrl', 'symbolUrl']);

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Could not read image.'));
    reader.readAsDataURL(blob);
  });
}

async function portableImageUrl(value: string, cache: Map<string, string>): Promise<string> {
  if (!value || value.startsWith('data:')) return value;
  if (cache.has(value)) return cache.get(value) as string;

  try {
    const resolved = new URL(value, window.location.href);
    if (!['http:', 'https:'].includes(resolved.protocol)) return value;
    const response = await fetch(resolved.href, { cache: 'no-store' });
    if (!response.ok) return value;
    const blob = await response.blob();
    if (!blob.type.startsWith('image/')) return value;
    const dataUrl = await blobToDataUrl(blob);
    cache.set(value, dataUrl);
    return dataUrl;
  } catch {
    return value;
  }
}

async function makePortable(value: unknown, cache: Map<string, string>): Promise<unknown> {
  if (Array.isArray(value)) {
    return Promise.all(value.map((item) => makePortable(item, cache)));
  }
  if (!value || typeof value !== 'object') return value;

  const input = value as Record<string, unknown>;
  const output: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(input)) {
    if (IMAGE_KEYS.has(key) && typeof item === 'string') {
      output[key] = await portableImageUrl(item, cache);
    } else {
      output[key] = await makePortable(item, cache);
    }
  }
  return output;
}

function visibleCanvasThumbnail(): string | undefined {
  const canvases = Array.from(
    document.querySelectorAll<HTMLCanvasElement>('.sheet-viewport canvas.lower-canvas'),
  );
  const canvas = canvases.find((candidate) => {
    const rect = candidate.getBoundingClientRect();
    return candidate.isConnected && rect.width > 20 && rect.height > 20;
  });
  if (!canvas) return undefined;

  try {
    return canvas.toDataURL('image/png', 0.72);
  } catch {
    return undefined;
  }
}

export default function SavePageTemplateModal({
  page,
  thumbnailDataUrl,
  onSaved,
  onCancel,
}: Props) {
  const pageRef = useRef(page);
  pageRef.current = page;

  const [name, setName] = useState(page.sheetTitle || 'Page Template');
  const [preview, setPreview] = useState(thumbnailDataUrl || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!preview) setPreview(visibleCanvasThumbnail() || '');
  }, [preview]);

  const doSave = async () => {
    if (!name.trim()) return;
    setLoading(true);
    setError('');

    try {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

      const thumbnail = visibleCanvasThumbnail() || preview || thumbnailDataUrl;
      if (thumbnail && !preview) setPreview(thumbnail);

      const portable = await makePortable(
        structuredClone(pageRef.current),
        new Map<string, string>(),
      ) as PageModel;

      await savePageTemplate(preparePageTemplatePayload(portable), name.trim(), thumbnail);
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Save Page as Template</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>
        <div className="modal-body">
          <p className="cw-note">
            Saves the current page canvas, image data, blocks, and layout. Saving the
            same name again updates the existing template instead of creating another copy.
          </p>

          {preview ? (
            <div style={{ marginBottom: 12, border: '1px solid #c8cdd4', background: '#f5f6f8', padding: 8 }}>
              <img
                src={preview}
                alt="Template preview"
                style={{ display: 'block', width: '100%', maxHeight: 220, objectFit: 'contain' }}
              />
            </div>
          ) : (
            <p className="cw-note">The template will still save, but this page has no visible canvas thumbnail.</p>
          )}

          <div className="field">
            <label htmlFor="tpl-name">Template name</label>
            <input
              id="tpl-name"
              type="text"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && name.trim() && !loading) void doSave();
              }}
            />
          </div>
          {error && <p className="modal-error">{error}</p>}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button
            className="btn btn-primary"
            disabled={loading || !name.trim()}
            onClick={() => void doSave()}
          >
            {loading ? 'Saving page and images…' : 'Save / Update Template'}
          </button>
        </div>
      </div>
    </div>
  );
}
