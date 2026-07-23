import React from 'react';
import { createRoot } from 'react-dom/client';
import './clipboardBridge';
import App from './App';
import HomeApp from './HomeApp';
import './styles/app.css';
import './styles/sheet.css';
import './styles/sourceParity.css';
import './styles/home.css';

function Root() {
  const params = new URLSearchParams(window.location.search);
  const editorMode = params.get('editor') === '1' || params.get('print') === '1';
  return editorMode ? <App /> : <HomeApp />;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
