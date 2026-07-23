import { useEffect } from 'react';
import App from './App';

function visibleButton(label: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => button.textContent?.trim() === label && button.offsetParent !== null && !button.disabled);
}

function projectIdFromUrl(): string {
  return new URLSearchParams(window.location.search).get('project') || '';
}

function projectHomeUrl(): string {
  const projectId = projectIdFromUrl();
  return projectId ? `/app?project=${encodeURIComponent(projectId)}` : '/app';
}

function helpUrl(): string {
  const projectId = projectIdFromUrl();
  const params = new URLSearchParams({ editor: '1', help: '1' });
  if (projectId) params.set('project', projectId);
  return `/app?${params.toString()}`;
}

export default function EditorEntry() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const openMapper = params.get('openSymbolMapper') === '1';
    const openLegend = params.get('openSymbolLegend') === '1';
    if (!openMapper && !openLegend) return;

    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (attempts > 160) {
        window.clearInterval(timer);
        return;
      }

      if (openMapper) {
        const symbolsTab = Array.from(document.querySelectorAll<HTMLButtonElement>('.ribbon-tab'))
          .find((button) => button.textContent?.trim() === 'Symbols');
        symbolsTab?.click();
        const action = visibleButton('Open Symbol Mapper');
        if (!action) return;
        action.click();
      } else {
        const insertTab = Array.from(document.querySelectorAll<HTMLButtonElement>('.ribbon-tab'))
          .find((button) => button.textContent?.trim() === 'Insert');
        insertTab?.click();
        const action = visibleButton('Symbol Legend');
        if (!action) return;
        action.click();
      }

      params.delete('openSymbolMapper');
      params.delete('openSymbolLegend');
      window.history.replaceState({}, '', `/app?${params.toString()}`);
      window.clearInterval(timer);
    }, 125);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="editor-entry-shell">
      <nav className="editor-global-nav" aria-label="Singh360 application navigation">
        <button type="button" onClick={() => window.location.assign(projectHomeUrl())} title="Return to this project's Project Home">
          Project Home
        </button>
        <button type="button" onClick={() => window.open('/component-catalog', '_blank', 'noopener,noreferrer')} title="Open the Component Builder / catalog workbench">
          Components
        </button>
        <button type="button" onClick={() => window.location.assign(helpUrl())} title="Open Singh360 workflow help">
          Help
        </button>
      </nav>
      <App />
    </div>
  );
}
