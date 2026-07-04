import type { PageModel, ProjectModel } from '../../model/types';
import { classifyPageFamily } from '../../model/emsNumbering';

interface Props {
  project: ProjectModel;
  page: PageModel;
}

/**
 * Generated Sheet Index / TOC for pages with pageType="index".
 *
 * Renders a clean table built from the CURRENT included pages. This is NOT a
 * raw workbook dump — it is always in sync with the actual package state.
 * Never scrolls; the normalized sheet body enforces overflow:hidden, so if
 * the list is too long the workbook importer or compose_pages must split it
 * into continuation sheets (0.1a, 0.1b).
 */
export default function GeneratedIndexRenderer({ project }: Props) {
  const included = (project.pages ?? []).filter((p) => p.include);

  if (!included.length) {
    return <div className="np-index np-empty">No included sheets — add or include pages to generate the index.</div>;
  }

  return (
    <div className="np-index">
      <table className="np-index-table">
        <thead>
          <tr>
            <th className="ni-code">Sheet Code</th>
            <th className="ni-title">Sheet Title</th>
            <th className="ni-pg">Page</th>
            <th className="ni-fam">Family</th>
          </tr>
        </thead>
        <tbody>
          {included.map((p) => {
            const fam = classifyPageFamily(p);
            const famLabel = fam.kind === 'front' ? `0.x · ${fam.label}`
              : fam.kind === 'family' ? `${fam.series}.x · ${fam.label}`
              : fam.label;
            return (
              <tr key={p.id} className={p.generatedContinuation ? 'ni-cont' : ''}>
                <td className="ni-code">{p.displaySheetCode || p.sheetCode || '—'}</td>
                <td className="ni-title">
                  {p.sheetTitle}
                  {p.generatedContinuation && <span className="ni-cont-mark"> — CONTINUED</span>}
                </td>
                <td className="ni-pg">{p.pageNumber ?? '—'}</td>
                <td className="ni-fam">{famLabel}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
