from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def _local_origin(page_url: str) -> str:
    parsed = urlparse(page_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://127.0.0.1:8766"


def export_pdf_via_playwright(url: str, output_path: Path, width_in: float = 17.0, height_in: float = 11.0) -> tuple[bool, str]:
    local_origin = _local_origin(url)
    script = f'''import asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright

LOCAL_ORIGIN = {local_origin!r}
PAGE_URL = {url!r}
OUTPUT_PATH = r"{output_path}"
WIDTH_IN = {width_in}
HEIGHT_IN = {height_in}

def rewrite_asset_url(request_url: str) -> str:
    try:
        parsed = urlparse(request_url)
    except Exception:
        return request_url
    if parsed.path.startswith("/api/") or parsed.path.startswith("/static/"):
        return LOCAL_ORIGIN + parsed.path + (("?" + parsed.query) if parsed.query else "")
    return request_url

async def run_export():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={{"width":1632,"height":1056}})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        async def route_assets(route):
            target = rewrite_asset_url(route.request.url)
            if target == route.request.url:
                await route.continue_()
                return
            response = await route.fetch(url=target)
            await route.fulfill(response=response)

        await page.route("**/*", route_assets)
        await page.goto(PAGE_URL, wait_until="networkidle")
        await page.wait_for_selector(
            "body[data-print-ready='1'], body[data-print-error]",
            timeout=30000,
        )
        print_error = await page.locator("body").get_attribute("data-print-error")
        if print_error:
            raise RuntimeError(f"Print renderer did not become ready: {{print_error}}")
        blocking = [
            e for e in errors
            if not e.startswith("fabric: Error loading ")
        ]
        if blocking:
            raise RuntimeError("; ".join(blocking[:20]))
        await page.pdf(
            path=OUTPUT_PATH,
            width=f"{{WIDTH_IN}}in",
            height=f"{{HEIGHT_IN}}in",
            print_background=True,
            prefer_css_page_size=False,
            margin={{"top":"0in","bottom":"0in","left":"0in","right":"0in"}},
        )
        await browser.close()

asyncio.run(run_export())
'''

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return False, "Playwright export timed out after 180 seconds"

    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "Playwright export failed")[-3000:]

    return True, ""
