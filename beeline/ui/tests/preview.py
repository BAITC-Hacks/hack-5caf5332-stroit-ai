"""Small browser check used after each screen. Requires Python Playwright + Chromium."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for screen in (sys.argv[1:] or ["audience", "pilots", "plan"]):
        for width in [1440, 375]:
            page.set_viewport_size({"width": width, "height": 1000 if width > 600 else 812})
            page.goto(f"http://127.0.0.1:4173/?screen={screen}")
            page.locator("h1").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow: {screen} at {width}"
            page.screenshot(path=str(root / "tests" / f"{screen}-{width}.png"), full_page=True)
            print(f"PASS {screen}: {width}px, no horizontal overflow, screenshot captured")
    assert not errors, errors
    browser.close()
