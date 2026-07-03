from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def export_pdf_via_playwright(url: str, output_path: Path) -> tuple[bool, str]:
    script = f'''import asyncio\nfrom playwright.async_api import async_playwright\n\nasync def run_export():\n    async with async_playwright() as p:\n        browser = await p.chromium.launch()\n        page = await browser.new_page(viewport={{"width":1632,"height":1056}})\n        errors = []\n        page.on("pageerror", lambda e: errors.append(str(e)))\n        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)\n        await page.goto("{url}", wait_until="networkidle")\n        await page.wait_for_timeout(1200)\n        if errors:\n            raise RuntimeError("; ".join(errors[:20]))\n        await page.pdf(path=r"{output_path}", width="17in", height="11in", landscape=True, print_background=True, margin={{"top":"0in","bottom":"0in","left":"0in","right":"0in"}})\n        await browser.close()\n\nasyncio.run(run_export())\n'''

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "Playwright export timed out after 120 seconds"

    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "Playwright export failed")[-3000:]

    return True, ""
