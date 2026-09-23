"""Historical fixture-UI suite (v1), not valid for the connected v2 workspace.

Kept for reference only. Current verification: tests/test_agent.py,
tests/test_server.py and the browser checks recorded in AUDIT-CONNECTED.md.
"""
raise SystemExit("Legacy fixture UI suite: see AUDIT-CONNECTED.md for current checks")
import csv
import io
import json
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:4173"
OUT = ROOT / "tests" / "results"
OUT.mkdir(exist_ok=True)


def tab_to(page, selector):
    for _ in range(100):
        if page.locator(selector).evaluate("el => el === document.activeElement"):
            style = page.locator(selector).evaluate("el => getComputedStyle(el).outlineStyle")
            assert style != "none", f"No keyboard focus outline: {selector}"
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"Not reachable by Tab: {selector}")


def activate(page, selector):
    tab_to(page, selector)
    page.keyboard.press("Enter")


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.url


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="ru-RU", accept_downloads=True)
    page = context.new_page()
    errors, violations = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    matrix = 0
    axe_runs = 0
    for width in ([] if "--keyboard-only" in sys.argv else [320, 375, 768, 1024, 1440]):
        page.set_viewport_size({"width": width, "height": 812 if width < 600 else 1000})
        for screen in ["audience", "pilots", "plan"]:
            for state in ["ready", "loading", "empty", "error"]:
                page.goto(f"{BASE}/?screen={screen}&state={state}")
                expect(page.locator("h1")).to_be_visible()
                no_overflow(page)
                assert page.locator("h1").count() == 1
                if state != "ready":
                    expect(page.locator("#state-title")).to_be_visible()
                if width in [375, 1440]:
                    page.add_script_tag(path=str(ROOT / "node_modules" / "axe-core" / "axe.min.js"))
                    result = page.evaluate("""async () => (await axe.run(document, {
                        runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa','best-practice']}
                    })).violations.map(v => ({id:v.id, impact:v.impact, nodes:v.nodes.map(n => ({target:n.target, summary:n.failureSummary}))}))""")
                    axe_runs += 1
                    if result:
                        violations.append({"screen": screen, "state": state, "width": width, "violations": result})
                    page.screenshot(path=str(OUT / f"{screen}-{state}-{width}.png"), full_page=True)
                matrix += 1
        print(f"PASS layout matrix: {width}px, 12 screen/state combinations", flush=True)

    print("AXE FINDINGS: " + json.dumps(violations, ensure_ascii=False), flush=True)
    for width in [1440, 375]:
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(BASE)
        activate(page, ".skip-link")
        expect(page.locator("#main")).to_be_focused()
        tab_to(page, "#segment-search")
        page.keyboard.type("tariff_4")
        expect(page.locator(".data-table tbody tr")).to_have_count(1)
        page.keyboard.press("ControlOrMeta+A")
        page.keyboard.type("no-matching-segment")
        expect(page.get_by_text("Таких сегментов нет", exact=True)).to_be_visible()
        activate(page, "#filters [data-action='clear-filters']")
        expect(page.locator(".data-table tbody tr")).to_have_count(6)
        tab_to(page, "#arpu-filter")
        page.keyboard.press("Home")
        page.keyboard.press("ArrowDown")
        expect(page.locator(".data-table tbody tr")).to_have_count(2)
        activate(page, "[data-detail='s1']")
        expect(page.locator("dialog")).to_be_visible()
        for _ in range(3):
            page.keyboard.press("Tab")
            assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)")
        page.keyboard.press("Escape")
        expect(page.locator("[data-detail='s1']")).to_be_focused()
        expect(page).not_to_have_url(re.compile("detail="))
        page.reload()
        expect(page.locator(".data-table tbody tr")).to_have_count(2)

        activate(page, ".main-nav [data-screen='pilots']")
        expect(page.locator(".pilot-row")).to_have_count(6)
        activate(page, "[data-pilot-detail='p4']")
        expect(page.locator("#dialog-content .negative")).to_contain_text("2,6")
        page.keyboard.press("Escape")
        activate(page, "#run-pilot")
        expect(page.locator("#run-pilot")).to_have_attribute("aria-disabled", "true")
        activate(page, "[data-action='cancel-pilot']")
        expect(page.locator(".pilot-row")).to_have_count(6)
        activate(page, "#run-pilot")
        page.keyboard.press("Enter")
        expect(page.locator(".pilot-row")).to_have_count(7, timeout=4000)
        expect(page.locator("#run-pilot")).to_be_focused()
        assert "extra=1" in page.url
        tab_to(page, "#channel-filter")
        page.keyboard.press("End")
        expect(page.get_by_text("Пилотов в этом канале нет", exact=True)).to_be_visible()
        activate(page, "[data-action='all-channels']")
        expect(page.locator(".pilot-row")).to_have_count(7)

        activate(page, ".main-nav [data-screen='plan']")
        expect(page.locator("input[name='campaign']:checked")).to_have_count(2)
        expect(page.locator("#select-c2")).not_to_be_checked()
        expect(page.locator("#export-csv")).to_be_enabled()
        before = page.locator(".estimate-value").inner_text()
        tab_to(page, "#select-c4")
        page.keyboard.press("Space")
        expect(page.locator(".risk-review")).to_be_visible()
        expect(page.locator("#export-csv")).to_be_disabled()
        expect(page.locator("#select-c4")).to_be_focused()
        tab_to(page, "#ack-risk")
        page.keyboard.press("Space")
        expect(page.locator("#export-csv")).to_be_enabled()
        page.reload()
        expect(page.locator("#export-csv")).to_be_disabled()
        expect(page.locator("#ack-risk")).not_to_be_checked()
        tab_to(page, "#select-c4")
        page.keyboard.press("Space")
        expect(page.locator("#export-csv")).to_be_enabled()
        assert page.locator(".estimate-value").inner_text() == before
        activate(page, "[data-id='c3'][data-move='up']")
        assert page.locator(".campaign-row").nth(0).get_attribute("data-campaign") == "c3"
        expect(page.locator("#select-c3")).to_be_focused()
        page.reload()
        assert page.locator(".campaign-row").nth(0).get_attribute("data-campaign") == "c3"
        tab_to(page, "#export-csv")
        with page.expect_download() as download:
            page.keyboard.press("Enter")
        rows = list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text())))
        assert len(rows) == 2
        assert [r["campaign_name"] for r in rows] == ["demo_c3_sms", "demo_c1_sms"]
        assert list(rows[0]) == ["campaign_name", "filter_arpu_segment", "filter_data_segment", "filter_call_segment", "filter_current_tariff", "target_tariff", "channel"]
        tab_to(page, "[data-action='export-audit']")
        with page.expect_download() as download:
            page.keyboard.press("Enter")
        audit = json.loads(Path(download.value.path()).read_text())
        assert audit["demo"] is True
        assert audit["totals"]["pilotCost"] == 2240
        assert audit["totals"]["pilotContacts"] == 740
        assert audit["totals"]["cost"] == 24400
        for key in ["c1", "c3"]:
            tab_to(page, f"#select-{key}")
            page.keyboard.press("Space")
        expect(page.locator(".plan-empty")).to_be_visible()
        expect(page.locator("#export-csv")).to_be_disabled()
        activate(page, "[data-action='restore-plan']")
        expect(page.locator("input[name='campaign']:checked")).to_have_count(2)
        for screen in ["audience", "pilots", "plan"]:
            page.goto(f"{BASE}/?screen={screen}&state=error")
            activate(page, "[data-action='retry']")
            expect(page.locator("#state-title")).to_contain_text("Загружаем")
            expect(page.locator("#state-title")).to_have_count(0, timeout=4000)
            expect(page.locator("#main")).to_be_focused()
            page.goto(f"{BASE}/?screen={screen}&state=empty")
            activate(page, "[data-action='recover']")
            expect(page.locator("#state-title")).to_have_count(0)
            page.goto(f"{BASE}/?screen={screen}&state=loading")
            activate(page, "[data-action='recover']")
            expect(page.locator("#state-title")).to_have_count(0)
        no_overflow(page)
        print(f"PASS keyboard workflow: {width}px; filters, dialogs, pilots, cancel, selection, reorder, exports, all state recovery", flush=True)

    page.goto(f"{BASE}/?screen=pilots&extra=14")
    expect(page.locator(".pilot-row")).to_have_count(20)
    expect(page.locator("#run-pilot")).to_be_disabled()
    page.goto(BASE)
    activate(page, "[data-detail='s1']")
    page.go_back()
    expect(page.locator("dialog")).not_to_be_visible()
    page.go_forward()
    expect(page.locator("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page).not_to_have_url(re.compile("detail="))
    page.goto(f"{BASE}/?screen=audience&detail=s1")
    expect(page.locator("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{BASE}/?screen=plan&state=loading")
    assert page.locator(".loading-rail span").first.evaluate("el => getComputedStyle(el).animationName") == "none"
    page.goto(f"{BASE}/?screen=plan&selected=c1,c2,c3,c4&order=c3,c1,c4,c2")
    expect(page.locator(".validation-error")).to_be_visible()
    expect(page.locator("#export-csv")).to_be_disabled()
    no_overflow(page)
    assert not errors, errors
    print(f"Browser: {browser.version}. Layout matrix: {matrix}; axe runs: {axe_runs}; JS errors: {len(errors)}", flush=True)
    print(json.dumps(violations, ensure_ascii=False, indent=2), flush=True)
    browser.close()
    assert not violations, "Accessibility violations listed above"
