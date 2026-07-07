import type { PageModel } from '../../model/types';

interface Props {
  page: PageModel;
}

/**
 * Singh360 standard orange title band (renderProfile = singh360_standard_table).
 *
 * A full-width orange/gold band with the black, centered sheet title sits at the
 * top of every non-cover table/instruction/schedule page, with an optional
 * light-gray project/subtitle row beneath it. This replaces the old dark/black
 * worksheet title bars so the whole package reads as one uniform Singh360 set.
 */
export default function SheetTitleBand({ page }: Props) {
  // Never double the "— CONTINUED" marker; the band shows it once.
  const cleanTitle = (page.sheetTitle || 'Untitled Sheet')
    .replace(/\s*[—-]\s*CONTINUED\s*$/i, '')
    .trim();
  const isCont = !!page.continuationOf || !!page.generatedContinuation;
  const subtitle = page.sheetTab && page.sheetTab !== cleanTitle ? page.sheetTab : '';

  return (
    <div className="np-title-band-wrap" data-band="orange">
      <div className="np-title-band">
        <span className="np-title-band-text">{cleanTitle}</span>
        {isCont && <span className="np-title-band-cont">— CONTINUED</span>}
      </div>
      {subtitle && <div className="np-subtitle-band">{subtitle}</div>}
    </div>
  );
}
