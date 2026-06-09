import re

file_path = '../Singh360 Dashboard/index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the style block
style_replacement = '''  <!-- Singh360 Shared Shell CSS -->
  <link rel="stylesheet" href="./src/shared_ui/singh360-theme.css" onerror="this.onerror=null;this.href='';console.warn('Shared theme CSS not found, using fallback root variables.')">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    
    :root {
      /* Shared Theme Colors Mapped */
      --bg:        #fafafa;
      --surface:   #ffffff;
      --surface-2: #f8fafc;
      --surface-3: #f1f5f9;
      --border:    #e5e7eb;
      --border-2:  #cbd5e1;
      --text-1:    #1f2937;
      --text-2:    #475569;
      --text-3:    #64748b;
      --g-blue:    #019CDC;
      --g-blue-d:  #007ba8;
      --g-green:   #10b981;
      --g-amber:   #f59e0b;
      --g-red:     #ef4444;

      --sidebar-w: 240px;
      --topbar-h: 64px;
      
      --font: 'Outfit', 'Inter', system-ui, sans-serif;
      --mono: 'Cascadia Code', Consolas, 'Courier New', monospace;
    }

    html, body {
      margin: 0;
      height: 100vh;
      width: 100vw;
      background: var(--bg);
      color: var(--text-1);
      font-family: var(--font);
      font-size: 14px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      display: flex;
      overflow: hidden;
    }

    /* -- GLOBAL LEFT SIDEBAR -- */
    #sidebar {
      width: var(--sidebar-w);
      min-width: var(--sidebar-w);
      background: #FBFCFE;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
      z-index: 50;
    }

    .sb-brand {
      height: var(--topbar-h);
      min-height: var(--topbar-h);
      display: flex;
      align-items: center;
      justify-content: center;
      border-bottom: 1px solid var(--border);
    }

    .sb-brand img {
      height: 40px;
      object-fit: contain;
    }

    .sb-scroll {
      flex: 1;
      padding: 16px 0;
      overflow-y: auto;
    }

    .sb-section { margin-bottom: 2px; }

    .sb-section-label {
      padding: 14px 16px 4px 24px;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-3);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      user-select: none;
    }

    .sb-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 16px 10px 24px;
      margin: 2px 12px;
      border-radius: 6px;
      color: #004c70;
      font-size: 14px;
      font-weight: 500;
      text-decoration: none;
      transition: background 0.15s;
    }

    .sb-item:hover { background: #e5e7eb; }
    .sb-item.active {
      background: #ffffff;
      font-weight: 600;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }

    .sb-item svg { width: 20px; height: 20px; flex-shrink: 0; opacity: 0.8; }
    .sb-item.active svg { color: var(--g-blue); opacity: 1; }

    .sb-divider { height: 1px; background: var(--border); margin: 6px 12px; }

    /* -- MAIN CONTENT WRAPPER -- */
    #main {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    #topbar {
      height: var(--topbar-h);
      min-height: var(--topbar-h);
      background: #004c70;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
      display: flex;
      align-items: center;
      padding: 0 24px;
      justify-content: space-between;
      z-index: 40;
    }

    .tb-crumb, .tb-sep { display: none; }
    .tb-title {
      font-size: 18px;
      font-weight: 600;
      color: #ffffff;
      letter-spacing: 0.02em;
    }
    .tb-badge {
      font-size: 11px; font-weight: 600; color: #019CDC; background: #e0f2fe;
      padding: 4px 10px;
      border: 1px solid #bae6fd;
      border-radius: 20px;
      letter-spacing: 0.05em; text-transform: uppercase;
    }

    /* -- VIEW CANVAS -- */
    .view-canvas {
      flex: 1;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 32px 32px 64px;
      display: none;
    }
    .view-canvas.active-view { display: block; }
    
    /* -- TABS -- */
    #view-tabs {
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      display: flex;
      gap: 16px;
      background: #ffffff;
      height: 48px;
    }
    .view-tab {
      background: transparent;
      color: var(--text-2);
      border: none;
      border-bottom: 2px solid transparent;
      font-size: 14px;
      font-weight: 500;
      padding: 0 4px;
      cursor: pointer;
      transition: color 0.15s, border-color 0.15s;
    }
    .view-tab:hover { color: #004c70; }
    .view-tab.active { color: #019CDC; border-color: #019CDC; font-weight: 600; }

    .gallery-header {
      display: flex;
      align-items: baseline;
      gap: 10px;
      margin-bottom: 24px;
    }
    .gallery-title {
      font-size: 24px; font-weight: 600;
      color: #004c70; letter-spacing: -0.01em;
    }
    .gallery-meta { font-size: 13px; color: var(--text-2); font-weight: 400; }

    .gallery-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
      gap: 16px;
    }

    /* -- GALLERY BUILDER -- */
    .builder-wrap {
      border: 1px solid var(--border);
      background: var(--surface);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      display: grid;
      gap: 16px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .builder-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .builder-field {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .builder-field label {
      font-size: 12px;
      color: var(--text-2);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .builder-input,
    .builder-textarea {
      width: 100%;
      border: 1px solid var(--border-2);
      border-radius: 8px;
      background: #ffffff;
      color: var(--text-1);
      padding: 10px 14px;
      font-family: var(--font);
      font-size: 14px;
      outline: none;
      transition: border-color .15s, box-shadow .15s;
    }
    .builder-input:focus,
    .builder-textarea:focus { border-color: var(--g-blue); box-shadow: 0 0 0 3px rgba(1, 156, 220, 0.15); }
    .builder-textarea {
      min-height: 180px;
      resize: vertical;
      font-family: var(--mono);
      line-height: 1.5;
    }
    .builder-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 8px;
    }
    .btn {
      border: 1px solid var(--border-2);
      background: #ffffff;
      color: var(--text-2);
      border-radius: 6px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all .15s;
    }
    .btn:hover { color: var(--text-1); border-color: var(--g-blue); background: #f0f9ff; }
    .btn-primary { color: #ffffff; border-color: var(--g-blue); background: var(--g-blue); }
    .btn-primary:hover { color: #ffffff; background: var(--g-blue-d); border-color: var(--g-blue-d); }
    .builder-note { font-size: 13px; color: var(--text-3); }

    .gallery-custom-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
    }

    /* -- CARD -- */
    .card {
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      cursor: pointer;
      transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .card:hover { transform: translateY(-2px); border-color: var(--g-blue); box-shadow: 0 10px 15px -3px rgba(0,76,112, 0.15); }
    .card.highlight { border-color: var(--g-blue); box-shadow: 0 0 0 2px rgba(1,156,220,0.25); }
    .card.highlight-new { border-color: var(--g-blue); box-shadow: 0 0 0 1px rgba(1,156,220,0.25), 0 10px 20px rgba(1,156,220,0.15); }
    .card.highlight-new .card-type { color: var(--g-blue); }

    /* -- OVERVIEW (App Central index) -- */
    .ov-hero {
      border: 1px solid var(--border); border-radius: 16px;
      background: #ffffff;
      padding: 36px 32px; margin-bottom: 32px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      position: relative;
      overflow: hidden;
    }
    .ov-hero::before {
      content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
      background: var(--g-blue);
    }
    .ov-hero-badge {
      display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
      color: #004c70; background: #e0f2fe;
      padding: 4px 12px; border-radius: 20px; margin-bottom: 16px;
    }
    .ov-hero-title { font-size: 32px; font-weight: 600; letter-spacing: -0.02em; color: #004c70; margin-bottom: 12px; }
    .ov-hero-sub { font-size: 15px; color: var(--text-2); max-width: 700px; line-height: 1.6; }
    .ov-stats { display: flex; flex-wrap: wrap; gap: 32px; margin-top: 28px; padding-top: 24px; border-top: 1px solid var(--border); }
    .ov-stat { display: flex; flex-direction: column; gap: 2px; }
    .ov-stat-n { font-size: 24px; font-weight: 600; color: var(--g-blue); }
    .ov-stat-l { font-size: 11px; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }

    .ov-section { margin-bottom: 32px; }
    .ov-section-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 16px; }
    .ov-section-title { font-size: 18px; font-weight: 600; color: #004c70; }
    .ov-section-meta { font-size: 13px; color: var(--text-3); }

    .ov-flow { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 16px; }
    .ov-step { display: flex; gap: 14px; padding: 16px; border: 1px solid var(--border); border-radius: 12px; background: #ffffff; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
    .ov-step-num { width: 28px; height: 28px; flex-shrink: 0; border-radius: 50%; background: #e0f2fe; color: var(--g-blue); font-size: 14px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
    .ov-step-body { display: flex; flex-direction: column; gap: 4px; }
    .ov-step-body b { font-size: 14px; color: var(--text-1); font-weight: 600; }
    .ov-step-body span { font-size: 13px; color: var(--text-2); line-height: 1.5; }

    .ov-apps { display: grid; grid-template-columns: repeat(auto-fill, minmax(335px, 1fr)); gap: 16px; }
    .ov-app { display: flex; gap: 16px; padding: 20px; border: 1px solid var(--border); border-radius: 12px; background: #ffffff; transition: border-color .15s, box-shadow .15s; box-shadow: 0 1px 3px rgba(0,0,0,0.04); cursor: default; }
    .ov-app:hover { border-color: var(--g-blue); box-shadow: 0 6px 12px rgba(0,76,112,0.1); }
    .ov-app.live { border-color: #bae6fd; }
    .ov-app-icon { width: 44px; height: 44px; border-radius: 10px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
    .ov-app-icon svg { width: 22px; height: 22px; }
    .ov-app-icon.c-parser { background: #e0f2fe; color: #019CDC; }
    .ov-app-icon.c-catalog { background: #d1fae5; color: #10b981; }
    .ov-app-icon.c-compliance { background: #e0f2fe; color: #019CDC; }
    .ov-app-icon.c-broadcast { background: #fef08a; color: #eab308; }
    .ov-app-icon.c-smartdraw { background: #e0f2fe; color: #019CDC; }
    .ov-app-main { min-width: 0; flex: 1; display:flex; flex-direction:column; }
    .ov-app-name { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #004c70; }
    .ov-tag { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; padding: 3px 8px; border-radius: 12px; }
    .ov-tag.static { background: #f1f5f9; color: var(--text-2); border: 1px solid var(--border); }
    .ov-tag.live { background: #e0f2fe; color: var(--g-blue); border: 1px solid #bae6fd; }
    .ov-app-desc { font-size: 13px; color: var(--text-2); line-height: 1.5; margin: 8px 0 10px; }
    .ov-app-how { font-size: 12px; color: var(--text-2); line-height: 1.5; padding: 8px; background: var(--surface-2); border-radius:8px;}
    .ov-app-how b { color: var(--text-1); font-weight: 600; }
    .ov-app-links { display: flex; gap: 16px; margin-top: 14px; }
    .ov-app-links a { font-size: 13px; font-weight: 600; color: var(--g-blue); text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
    .ov-app-links a:hover { color: var(--g-blue-d); text-decoration: underline; text-underline-offset: 2px; }
    .ov-app-links a.gh { color: var(--text-3); font-weight: 500; }
    .ov-app-links a.gh:hover { color: var(--text-1); text-decoration: none;}

    .ov-arch { background: #1e293b; border: 1px solid #0f172a; border-radius: 12px; padding: 20px 24px; font-family: var(--mono); font-size: 13px; line-height: 1.5; color: #e2e8f0; white-space: pre; overflow-x: auto; }
    .ov-note { font-size: 13px; color: var(--text-2); margin-top: 14px; line-height: 1.6; }
    .ov-note code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: var(--mono); font-size: 12px; color: #004c70; font-weight: 500;}

    .card-preview {
      width: 100%; height: 180px;
      background: #f1f5f9;
      border-bottom: 1px solid var(--border);
      overflow: hidden;
      position: relative;
    }

    .iframe-scaler {
      position: absolute; top: 0; left: 0;
      width: 1440px; height: 810px;
      transform-origin: top left;
    }
    .iframe-scaler iframe {
      width: 100%; height: 100%;
      border: none; pointer-events: none; display: block;
    }

    .card-preview-static {
      width: 100%; height: 100%;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      gap: 10px;
    }
    .preview-icon {
      width: 48px; height: 48px;
      border-radius: 12px;
      display: flex; align-items: center; justify-content: center;
      background: #ffffff; border: 1px solid var(--border);
    }
    .preview-label { font-size: 12px; color: var(--text-2); text-align: center; font-weight: 500; }
    .preview-sub   { font-size: 11px; color: var(--text-3); text-align: center; }

    .card-body { padding: 16px 20px 20px; display: flex; flex-direction: column; gap: 6px; }
    .card-title { font-size: 16px; font-weight: 600; color: #004c70; letter-spacing: 0; }
    .card-desc  { font-size: 13px; color: var(--text-2); line-height: 1.5; }
    .card-type  { font-size: 12px; color: var(--text-3); margin-top: 4px; font-weight: 500;}

    /* -- SCRATCHPAD -- */
    #scratchpad-bar {
      min-height: var(--pad-h);
      max-height: var(--pad-h);
      border-top: 1px solid var(--border);
      background: #ffffff;
      display: flex;
      flex-direction: column;
    }
    .pad-header { display: flex; align-items: center; gap: 8px; padding: 10px 24px 0; }
    .pad-label { font-size: 12px; font-weight: 600; color: #004c70; letter-spacing: 0.04em; text-transform: uppercase; }
    .pad-indicator { width: 8px; height: 8px; border-radius: 50%; background: var(--g-green); opacity: 0; transition: opacity 0.2s; flex-shrink: 0; }
    .pad-indicator.live { opacity: 1; }
    .pad-chars { margin-left: auto; font-size: 12px; color: var(--text-3); font-weight: 500;}
    #scratchpad {
      flex: 1;
      background: transparent; border: none; outline: none; resize: none;
      color: var(--text-1); font-family: var(--font); font-size: 14px;
      line-height: 1.6; padding: 8px 24px 16px;
      caret-color: var(--g-blue);
    }
    #scratchpad::placeholder { color: var(--text-3); }

    /* -- Iframe fallback overlay -- */
    .iframe-fallback {
      position: absolute; inset: 0;
      display: none;
      flex-direction: column; align-items: center; justify-content: center;
      gap: 12px; text-align: center; padding: 20px;
      background: rgba(255,255,255,0.9);
      backdrop-filter: blur(4px);
    }
    .iframe-fallback.show { display: flex; }
    .iframe-fallback p { font-size: 13px; font-weight: 500; color: var(--text-2); line-height: 1.6; margin: 0; }
    .iframe-fallback code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 12px; color: #004c70;}
    .open-btn {
      font-size: 13px; font-weight: 600; color: #ffffff;
      padding: 8px 18px;
      border-radius: 6px; background: var(--g-blue);
      cursor: pointer; text-decoration: none; transition: background 0.15s;
    }
    .open-btn:hover { background: var(--g-blue-d); }

    /* -- Card-actions link row -- */
    .card-action-row { padding: 0 20px 20px; display: flex; align-items: center; gap: 12px; }
    .card-action-link {
      font-size: 13px; color: var(--g-blue); text-decoration: none;
      font-weight: 600; display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 12px; border-radius: 6px; background: #f0f9ff; transition: all 0.15s; border: 1px solid #bae6fd;
    }
    .card-action-link:hover { background: #e0f2fe; border-color: #7dd3fc;}
    .card-gh-link {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 13px; font-weight: 500; color: var(--text-3);
      text-decoration: none; margin-left: auto;
      transition: color 0.15s; padding: 6px 12px; border-radius: 6px;
    }
    .card-gh-link:hover { color: var(--text-1); background: #f1f5f9; }
  </style>
</head>
<body>

<div id="shell">

  <!-- SIDEBAR -->
  <nav id="sidebar">
    <div class="sb-brand">
      <img src="https://ems.stogsdill.net/LOGO-750px.png" alt="Singh360 Logo" />
    </div>
    <div class="sb-scroll">
'''

# Find the start of the style block and replace down to the <div class="sb-scroll">
text = re.sub(r'  <style>.*<div class="sb-brand">.*?<img src="https://ems.stogsdill.net/logo.png".*?</div>.*?<div class="sb-section-label">Home</div>', style_replacement + '\\n      <div class="sb-section-label">Home</div>', text, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Done!')
