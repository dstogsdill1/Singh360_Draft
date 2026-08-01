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
          <p>Help version {HELP_VERSION}. Singh360 projects are self-contained drawing sets.</p>
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
          <article><b>Open</b><span>Open an active drawing project from Project Home. Every required page and asset lives in the Singh360 project package.</span></article>
          <article><b>Add / Import Page</b><span>Create a blank page or make a one-time project-local copy of a PDF, image, Excel worksheet, or CSV table.</span></article>
          <article><b>Edit</b><span>Use the page canvas, imported-table tools, properties, and Components browser. External source files are never updated.</span></article>
          <article><b>Archive / restore</b><span>Archive pages or projects recoverably, then restore them from Archived Pages or Archived Projects.</span></article>
          <article><b>Reorder / recode</b><span>Drag drawing pages or edit their title and sheet code. The app-managed cover, Sheet Index, and Page X of Y update from the project.</span></article>
          <article><b>Save and export</b><span>Save Project confirms the latest editor state. Export PDF regenerates the complete ordered set from included pages.</span></article>
        </div>
      </section>

      <section className="s360-help-section">
        <h2>Standalone source-of-truth rule</h2>
        <p>
          Imported files are source attachments only. Moving or disconnecting an original file does not affect
          a saved Singh360 drawing set, and Singh360 never writes changes back to that original.
        </p>
      </section>
    </main>
  );
}
