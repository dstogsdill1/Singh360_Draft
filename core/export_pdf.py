from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def export_pdf_via_playwright(url: str, output_path: Path, width_in: float = 17.0, height_in: float = 11.0) -> tuple[bool, str]:
    script = f'''import asyncio\nfrom playwright.async_api import async_playwright\n\nasync def run_export():\n    async with async_playwright() as p:\n        browser = await p.chromium.launch()\n        page = await browser.new_page(viewport={{"width":1632,"height":1056}})\n        errors = []\n        page.on("pageerror", lambda e: errors.append(str(e)))\n        await page.goto("{url}", wait_until="networkidle")\n        try:\n            await page.wait_for_selector("body[data-print-ready=\\'1\\']", timeout=15000)\n        except Exception:\n            pass\n        await page.wait_for_timeout(400)\n        if errors:\n            raise RuntimeError("; ".join(errors[:20]))\n        await page.pdf(path=r"{output_path}", width="{width_in}in", height="{height_in}in", print_background=True, prefer_css_page_size=False, margin={{"top":"0in","bottom":"0in","left":"0in","right":"0in"}})\n        await browser.close()\n\nasyncio.run(run_export())\n'''

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
