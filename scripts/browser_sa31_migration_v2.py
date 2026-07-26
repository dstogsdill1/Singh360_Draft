"""Playwright evidence for the migrated SA31 schema-V2 workflow."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / ".docs"
BASE = "http://127.0.0.1:8766"
OUTPUT = DOCS / "test_evidence" / "sa31_browser"
MIGRATION = (
    DOCS / "audits" / "sa31_schema_v2_source_library_20260726-135630"
    / "migration_apply.json"
)


def main() -> int:
    project_id = json.loads(MIGRATION.read_text("utf-8"))["newProjectId"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "projectId": project_id,
        "testedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "routes": {},
        "consoleErrors": [],
        "pageErrors": [],
        "httpFailures": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1050}, device_scale_factor=1
        )
        page = context.new_page()
        page.on(
            "console",
            lambda message: report["consoleErrors"].append(message.text)
            if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: report["pageErrors"].append(str(error)))
        page.on(
            "response",
            lambda response: report["httpFailures"].append(
                {"status": response.status, "url": response.url}
            ) if response.status >= 400 else None,
        )

        def capture(name: str, url: str, labels: list[str], full_page: bool = True):
            response = page.goto(url, wait_until="networkidle", timeout=120_000)
            page.wait_for_timeout(1200)
            body = page.locator("body").inner_text()
            missing = [label for label in labels if label not in body]
            if missing:
                raise AssertionError(f"{name} missing labels: {missing}")
            path = OUTPUT / f"{name}.png"
            page.screenshot(path=str(path), full_page=full_page)
            report["routes"][name] = {
                "url": url,
                "status": response.status if response else None,
                "labels": labels,
                "screenshot": str(path),
            }

        capture(
            "project_home",
            f"{BASE}/app",
            ["Project Home", "SA31", "New Project", "Archived Projects"],
        )
        page.get_by_role("button", name="Archived Projects").click()
        page.wait_for_function(
            "() => document.body.innerText.includes('Mi Tienda 03')",
            timeout=30_000,
        )
        archived_text = page.locator("body").inner_text()
        for label in ("Archived Projects", "Mi Tienda 03", "Template Platform E2E"):
            if label not in archived_text:
                raise AssertionError(f"Archived view missing {label}")
        archived_path = OUTPUT / "archived_projects.png"
        page.screenshot(path=str(archived_path), full_page=True)
        report["routes"]["archived_projects"] = {
            "screenshot": str(archived_path),
            "labels": ["Archived Projects", "Mi Tienda 03", "Template Platform E2E"],
        }

        capture(
            "new_project_wizard",
            f"{BASE}/app?view=new",
            ["New Project", "EMS Lighting / Dimming Integration", "EMS Full"],
        )
        capture(
            "sa31_home",
            f"{BASE}/app?project={project_id}",
            ["Project Home", "ACTIVE PROJECT", "24", "Included", "5", "Excluded"],
        )
        capture(
            "source_library",
            f"{BASE}/app?project={project_id}&view=sources",
            [
                "Source Library", "Upload Files", "Upload Folder", "Import ZIP",
                "New Folder", "SA31_EMS_Lighting_Workbook_V1.xlsx",
            ],
        )
        page.get_by_text("SA31_EMS_Lighting_Workbook_V1.xlsx", exact=True).click()
        page.wait_for_timeout(1000)
        preview_path = OUTPUT / "source_library_preview.png"
        page.screenshot(path=str(preview_path), full_page=True)
        preview_text = page.locator("body").inner_text()
        if "Source ID" not in preview_text or "SHA-256" not in preview_text:
            raise AssertionError("Source preview details did not render")
        report["routes"]["source_library_preview"] = {
            "screenshot": str(preview_path),
            "detailsVisible": True,
        }

        capture(
            "data_workspace",
            f"{BASE}/app?project={project_id}&view=data",
            ["Data Workspace", "Update Drawings", "SAVE + WRITE EXCEL"],
            full_page=False,
        )
        report["routes"]["data_workspace"]["canvasCount"] = page.locator("canvas").count()
        report["routes"]["data_workspace"]["coloredTabSignals"] = page.evaluate(
            """() => Array.from(document.querySelectorAll('*')).filter((element) => {
              const style = getComputedStyle(element);
              return ['rgb(34, 40, 49)', 'rgb(255, 192, 0)', 'rgb(245, 158, 11)',
                'rgb(37, 99, 235)', 'rgb(234, 88, 12)', 'rgb(79, 70, 229)',
                'rgb(124, 58, 237)', 'rgb(22, 163, 74)', 'rgb(156, 163, 175)']
                .includes(style.backgroundColor);
            }).length"""
        )

        capture(
            "page_editor",
            f"{BASE}/app?project={project_id}&mode=editor",
            ["SINGH360", "SAVE + WRITE EXCEL"],
            full_page=False,
        )
        page.locator('button[title="Open visual page manager"]:visible').first.click()
        page.wait_for_function(
            "() => document.body.innerText.includes('PROTECTED MANUAL')",
            timeout=15_000,
        )
        manager_text = page.locator("body").inner_text()
        for label in ("VISUAL PAGE MANAGER", "PROTECTED MANUAL", "PUBLISHED"):
            if label not in manager_text:
                raise AssertionError(f"Page manager missing {label}")
        cards = page.locator(".page-nav-card")
        colors = cards.evaluate_all(
            """cards => Array.from(new Set(cards.map(card =>
              getComputedStyle(card).borderLeftColor)))"""
        )
        excluded = page.locator(".page-nav-card.excluded").count()
        active = page.locator(".page-nav-card.active").count()
        manager_path = OUTPUT / "page_manager_colors.png"
        page.screenshot(path=str(manager_path), full_page=True)
        report["routes"]["page_manager"] = {
            "screenshot": str(manager_path),
            "cardCount": cards.count(),
            "borderColors": colors,
            "excludedCards": excluded,
            "activeCards": active,
            "protectedManual": manager_text.count("PROTECTED MANUAL"),
        }
        if excluded != 5 or active < 1 or len(colors) < 5:
            raise AssertionError(
                f"Page color/state evidence failed: excluded={excluded}, "
                f"active={active}, colors={colors}"
            )
        browser.close()

    ignored = ("favicon.ico",)
    report["consoleErrors"] = [
        item for item in report["consoleErrors"]
        if not any(token in item for token in ignored)
    ]
    report["httpFailures"] = [
        item for item in report["httpFailures"]
        if not any(token in item["url"] for token in ignored)
    ]
    if report["consoleErrors"] or report["pageErrors"] or report["httpFailures"]:
        raise AssertionError(json.dumps(report, indent=2))
    output = OUTPUT / "browser_report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
