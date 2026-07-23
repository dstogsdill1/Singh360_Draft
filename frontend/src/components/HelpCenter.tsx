import { HELP_VERSION, PAGE_ISSUE_STATUSES } from '../model/pageStatus';

interface Props {
  onClose: () => void;
}

export default function HelpCenter({ onClose }: Props) {
  return (
    <main className="s360-help-center">
      <header className="s360-help-head">
        <div>
          <div className="s360-help-eyebrow">SINGH360 DRAFT</div>
          <h1>Quick Help</h1>
          <p>Help version {HELP_VERSION}. This content matches workbook tab 3: <strong>00_HELP</strong>.</p>
        </div>
        <button type="button" className="s360-help-close" onClick={onClose}>Close Help</button>
      </header>

      <section className="s360-help-section">
        <h2>Page status: four distinct stages</h2>
        <div className="s360-help-status-grid">
          {PAGE_ISSUE_STATUSES.map((item) => (
            <article key={item.value} style={{ borderColor: item.color }}>
              <div className="s360-help-status-title" style={{ background: item.color }}>
                {item.confirmed ? '✓ ' : ''}{item.label}
              </div>
              <p>
                {item.value === 'draft' && 'Initial creation and active development.'}
                {item.value === 'draft_confirmed' && 'Engineer reviewed and confirmed the draft.'}
                {item.value === 'public' && 'Approved to go out for bid or external review.'}
                {item.value === 'public_confirmed' && 'Final approved publication before as-builts.'}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="s360-help-section">
        <h2>Include / Exclude is separate</h2>
        <div className="s360-help-callout">
          <strong>Include in Drawing Set</strong> controls the Sheet Index, Page X of Y, and export.
          An excluded page stays visible and editable, but its tab is gray.
        </div>
      </section>

      <section className="s360-help-section">
        <h2>Everyday tasks</h2>
        <div className="s360-help-steps">
          <article><b>Open</b><span>Open the saved project. The app checks the linked workbook before showing pages.</span></article>
          <article><b>Add a workbook page</b><span>Add the sheet and its 00_INDEX row. The permanent Page ID keeps it linked.</span></article>
          <article><b>Add an app page</b><span>Create it in Singh360. Saving creates or updates its workbook companion row and sheet.</span></article>
          <article><b>Images / attachments</b><span>Use the matching .a/.b source sheet. Replace the image there and sync.</span></article>
          <article><b>Reorder / renumber</b><span>Move pages in the app. Saving updates 00_INDEX order, codes, workbook tab order, Sheet Index, and Page X of Y.</span></article>
          <article><b>Export</b><span>Only included pages export. The generated Sheet Index is refreshed immediately before PDF export.</span></article>
        </div>
      </section>

      <section className="s360-help-section">
        <h2>Documentation rule</h2>
        <p>
          The app and workbook store the same Help Version. Automated tests fail when workflow code changes
          without updating the Help Center and workbook help version.
        </p>
      </section>
    </main>
  );
}
