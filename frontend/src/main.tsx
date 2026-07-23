import React from 'react';
import { createRoot } from 'react-dom/client';
import './clipboardBridge';
import App from './App';
import './styles/app.css';
import './styles/sheet.css';
import './styles/sourceParity.css';
import './styles/symbolMapper.css';
import './styles/textBoxFormatting.css';
import './styles/statusHelp.css';
import './styles/projectDashboard.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
