import React from 'react';
import { createRoot } from 'react-dom/client';
import './clipboardBridge';
import App from './App';
import '@univerjs/preset-sheets-core/lib/index.css';
import '@univerjs/preset-sheets-data-validation/lib/index.css';
import '@univerjs/preset-sheets-conditional-formatting/lib/index.css';
import './styles/app.css';
import './styles/sheet.css';
import './styles/sourceParity.css';
import './styles/symbolMapper.css';
import './styles/textBoxFormatting.css';
import './styles/statusHelp.css';
import './styles/projectDashboard.css';
import './styles/projectWorkspace.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
