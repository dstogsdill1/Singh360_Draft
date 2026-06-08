import re

file_path = '../Singh360_SmartDraw/start.html'

with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace root CSS variables
text = re.sub(
    r':root \{.*?\}',
    ':root {\\n      --bg: #fafafa; --surface: #ffffff; --surface-2: #f8fafc; --surface-3: #f1f5f9;\\n      --border: #e5e7eb; --border-2: #cbd5e1; --text-1: #1f2937; --text-2: #475569;\\n      --text-3: #64748b; --g-blue: #019CDC; --g-blue-d: #007ba8; --g-green: #10b981;\\n      --g-amber: #f59e0b; --g-red: #ef4444;\\n      --sidebar-w: 240px; --topbar-h: 64px;\\n      --font: \"Outfit\", \"Inter\", system-ui, sans-serif;\\n      --mono: \"Cascadia Code\", Consolas, \"Courier New\", monospace;\\n    }',
    text,
    flags=re.DOTALL
)

# Add link to shared css
if 'singh360-theme.css' not in text:
    text = text.replace('</head>', '  <link rel=\"stylesheet\" href=\"../Singh360 Dashboard/src/shared_ui/singh360-theme.css\">\\n</head>')

# Ensure wrap doesn't conflict with global overflow
text = re.sub(
    r'html, body \{.*?\}',
    'html, body {\\n      margin: 0; height: 100vh; width: 100vw;\\n      background: var(--bg); color: var(--text-1); font-family: var(--font);\\n      font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased;\\n      display: flex; overflow: hidden;\\n    }',
    text,
    flags=re.DOTALL
)

layout_injection = \"\"\"<body>
  <!-- GLOBAL SIDEBAR -->
  <aside id=\"global-sidebar\" style=\"width: var(--sidebar-w); min-width: var(--sidebar-w); background: #FBFCFE; border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; z-index: 50;\">
    <div class=\"sb-brand\" style=\"height: var(--topbar-h); display: flex; align-items: center; justify-content: center; border-bottom: 1px solid var(--border);\">
      <img src=\"https://ems.stogsdill.net/LOGO-750px.png\" alt=\"Singh360 Logo\" style=\"height: 40px; object-fit: contain;\" />
    </div>
    <nav class=\"sb-nav\" style=\"flex: 1; padding: 16px 0; overflow-y: auto;\">
      <a href=\"../Singh360 Dashboard/index.html\" class=\"sb-item\" style=\"display: flex; align-items: center; gap: 12px; padding: 10px 16px 10px 24px; margin: 2px 12px; border-radius: 6px; color: #004c70; font-size: 14px; font-weight: 500; text-decoration: none; transition: background 0.15s;\">App Central</a>
      <a href=\"../Singh360_Parser/index.html\" class=\"sb-item\" style=\"display: flex; align-items: center; gap: 12px; padding: 10px 16px 10px 24px; margin: 2px 12px; border-radius: 6px; color: #004c70; font-size: 14px; font-weight: 500; text-decoration: none; transition: background 0.15s;\">Parser</a>
      <a href=\"../Singh360_Catalog/index.html\" class=\"sb-item\" style=\"display: flex; align-items: center; gap: 12px; padding: 10px 16px 10px 24px; margin: 2px 12px; border-radius: 6px; color: #004c70; font-size: 14px; font-weight: 500; text-decoration: none; transition: background 0.15s;\">Catalog</a>
      <a href=\"../SINGH360 Compliance/index.html\" class=\"sb-item\" style=\"display: flex; align-items: center; gap: 12px; padding: 10px 16px 10px 24px; margin: 2px 12px; border-radius: 6px; color: #004c70; font-size: 14px; font-weight: 500; text-decoration: none; transition: background 0.15s;\">Compliance</a>
      <a href=\"http://localhost:8765/\" class=\"sb-item active\" style=\"display: flex; align-items: center; gap: 12px; padding: 10px 16px 10px 24px; margin: 2px 12px; border-radius: 6px; background: #ffffff; color: #019CDC; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.05); text-decoration: none;\">SmartDraw</a>
    </nav>
  </aside>

  <!-- MAIN WRAPPER -->
  <div id=\"main-wrapper\" style=\"flex: 1; display: flex; flex-direction: column; overflow: hidden;\">
    <!-- GLOBAL TOP NAVBAR -->
    <header id=\"topbar\" style=\"height: var(--topbar-h); min-height: var(--topbar-h); background: #004c70; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); display: flex; align-items: center; padding: 0 24px; justify-content: space-between; z-index: 40;\">
      <div class=\"tb-title\" style=\"font-size: 18px; font-weight: 600; color: #ffffff; letter-spacing: 0.02em;\">Singh360 Productivity Dashboard</div>
    </header>

    <!-- VIEWPORT -->
    <div id=\"viewport\" style=\"flex: 1; overflow-y: auto; position: relative; display: flex; flex-direction: column;\">
      <div class=\"wrap\" style=\"max-width: 960px; margin: 0 auto; padding: 30px 24px 60px; width: 100%;\">
\"\"\"
text = text.replace('<body>\\n  <div class=\"wrap\">', layout_injection)

closing_injection = \"\"\"    </footer>
      </div> <!-- end wrap -->
    </div> <!-- end viewport -->
  </div> <!-- end main-wrapper -->\"\"\"
text = text.replace('    </footer>\\n  </div>', closing_injection)

# Modify button colors inside code directly
text = text.replace('background:linear-gradient(135deg,#8ab4f8,#5a96f5);', 'background:var(--g-blue); border:1px solid var(--g-blue);')
text = text.replace('color:#202124;', 'color:#ffffff;')
text = text.replace('box-shadow:0 4px 16px rgba(66,133,244,0.3);', 'box-shadow:0 1px 2px rgba(0,0,0,0.05);')
text = text.replace('background:linear-gradient(135deg,#8ab4f8,#4285f4);', 'background:#e0f2fe;')
text = text.replace('stroke="#202124"', 'stroke="#ffffff"')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Done!')
