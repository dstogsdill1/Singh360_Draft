"""Generated, sanitized fixtures for Singh360 Draft regression tests."""
from __future__ import annotations

from pathlib import Path


def write_workbook(path: Path) -> Path:
    from openpyxl import Workbook

    workbook = Workbook()
    metadata = workbook.active
    metadata.title = "00_PROJECT_META"
    metadata.append(["Project Name", "Sanitized Regression Project"])
    metadata.append(["Workbook Schema Version", "2"])
    metadata.append(["Help Version", "test"])

    index = workbook.create_sheet("00_INDEX")
    index.append([
        "Include", "Order", "Sheet Code", "Sheet Tab", "Page Title",
        "Page ID", "Page Type",
    ])
    index.append(["YES", 1, "EMS 1.0", "Assets", "Asset Schedule", "", "table"])
    index.append(["YES", 2, "EMS 2.0", "Network", "Network Schedule", "", "table"])

    assets = workbook.create_sheet("Assets")
    assets.append(["Tag", "Description", "Quantity"])
    assets.append(["CTRL-01", "Generic Controller", 1])
    assets.append(["SENS-01", "Generic Temperature Sensor", 2])

    network = workbook.create_sheet("Network")
    network.append(["Device", "Protocol", "Address"])
    network.append(["CTRL-01", "BACnet/IP", "10.0.0.10"])
    workbook.save(path)
    return path


def write_pdf(path: Path) -> Path:
    import fitz

    document = fitz.open()
    page = document.new_page(width=11 * 72, height=8.5 * 72)
    page.insert_text((72, 72), "Sanitized Singh360 Draft PDF fixture")
    page.draw_rect(fitz.Rect(72, 100, 576, 360), color=(0, 0, 0))
    document.save(path)
    document.close()
    return path
