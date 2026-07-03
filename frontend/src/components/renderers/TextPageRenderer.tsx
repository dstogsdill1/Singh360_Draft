import type { PageBlock } from '../../model/types';

interface Props {
  block: PageBlock;
  onChange: (patch: Partial<PageBlock>) => void;
}

/** Renders a single text-family block (title, heading, paragraph, bullets, note). */
export default function TextPageRenderer({ block, onChange }: Props) {
  if (block.type === 'title') {
    return (
      <div
        className="np-title"
        contentEditable
        suppressContentEditableWarning
        onBlur={(e) => onChange({ text: e.currentTarget.textContent ?? '' })}
      >
        {block.text}
      </div>
    );
  }

  if (block.type === 'subtitle') {
    return (
      <div className="np-subtitle" contentEditable suppressContentEditableWarning onBlur={(e) => onChange({ text: e.currentTarget.textContent ?? '' })}>
        {block.text}
      </div>
    );
  }

  if (block.type === 'sectionHeading') {
    return (
      <div className="np-heading" contentEditable suppressContentEditableWarning onBlur={(e) => onChange({ text: e.currentTarget.textContent ?? '' })}>
        {block.text}
      </div>
    );
  }

  if (block.type === 'note') {
    return (
      <div className="np-note" contentEditable suppressContentEditableWarning onBlur={(e) => onChange({ text: e.currentTarget.textContent ?? '' })}>
        {block.text}
      </div>
    );
  }

  if (block.type === 'bulletList') {
    const items = block.items ?? [];
    return (
      <ul className="np-bullets">
        {items.map((it, i) => (
          <li
            key={i}
            contentEditable
            suppressContentEditableWarning
            onBlur={(e) => {
              const next = [...items];
              next[i] = e.currentTarget.textContent ?? '';
              onChange({ items: next });
            }}
          >
            {it}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <p className="np-paragraph" contentEditable suppressContentEditableWarning onBlur={(e) => onChange({ text: e.currentTarget.textContent ?? '' })}>
      {block.text}
    </p>
  );
}
