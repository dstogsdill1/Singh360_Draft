import type { PageModel } from '../../model/types';

interface Props {
  page: PageModel;
}

/**
 * Singh360 standard page header band (renderProfile = singh360_standard_table).
 *
 * A full-width dark-charcoal band with centered white sheet-title text sits at
 * the top of every non-cover table/instruction/schedule page, with an optional
 * light-gray project/subtitle row beneath it. Dark header + white text gives
 * strong black-and-white print contrast; the orange/gold table section bands
 * inside the table body (controller sections, schedule titles) are a separate,
 * unchanged accent — see core/table_style_profile.py.
 */
export default function SheetTitleBand({ page }: Props) {
  // Never double the "— CONTINUED" marker; the band shows it once.
  const cleanTitle = (page.sheetTitle || 'Untitled Sheet')
    .replace(/\s*[—-]\s*CONTINUED\s*$/i, '')
    .trim();
  const isCont = !!page.continuationOf || !!page.generatedContinuation;
  // Prefer the canonical sheet code in the subtitle so the top band agrees
  // with the title-block SHEET NO. (FINAL SA31 POLISH 4I, Phase B). Fall
  // back to the worksheet tab when no code is present.
  const code = (page.displaySheetCode || page.sheetCode || '').trim();
  const subtitle = code
    ? code
    : page.sheetTab && page.sheetTab !== cleanTitle
      ? page.sheetTab
      : '';

  return (
    <div className="np-title-band-wrap" data-band="dark">
      <div className="np-title-band">
        <span className="np-title-band-text">{cleanTitle}</span>
        {isCont && <span className="np-title-band-cont">— CONTINUED</span>}
      </div>
      {subtitle && <div className="np-subtitle-band">{subtitle}</div>}
    </div>
  );
}
