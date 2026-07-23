import React from 'react';
import { createRoot } from 'react-dom/client';
import './clipboardBridge';
import HomeApp from './HomeApp';
import EditorEntry from './EditorEntry';
import './styles/app.css';
import './styles/sheet.css';
import './styles/sourceParity.css';
import './styles/symbolMapper.css';
import './styles/textBoxFormatting.css';
import './styles/statusHelp.css';
import './styles/home.css';

function Root() {
  const params = new URLSearchParams(window.location.search);
  const editorMode = params.get('editor') === '1'
    || params.get('print') === '1'
    || params.get('help') === '1';
  return editorMode ? <EditorEntry /> : <HomeApp />;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
