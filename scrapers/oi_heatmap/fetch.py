"""
OI Heatmap Playwright fetcher.

fetch_all_tabs(product, session, headless) → dict
"""

from pathlib import Path

from playwright.async_api import async_playwright

from session import Session
from url_builder import build_url
from playwright_utils import safe_goto, expect_body, wait_for_updatepanel_idle
from .parser import parse_oi_heatmap_response

_SESSION_FILE = Path(__file__).parent.parent.parent / "data" / "session.json"
_RAW_DIR      = Path(__file__).parent.parent.parent / "data" / "raw" / "oi_heatmap"

TAB_BUTTONS = {
    "oi":        "lbOIMatrix",
    "oi_change": "lbOIChgMatrix",
    "volume":    "lbVolumeMatrix",
}

_STRIKES_DDL = (
    "#MainContent_ucViewControl_IntegratedVOIHeatMap"
    "_ucMatrixTB_ddlStrikes"
)


def _is_oi_data(r):
    """Match the AJAX POST responses that carry heatmap grid data."""
    return (
        "QuikStrikeView.aspx" in r.url
        and "IntegratedVOIHeatMap" in r.url
        and r.request.method == "POST"
        and r.status == 200
    )


async def fetch_all_tabs(
    product: str,
    session: Session,
    headless: bool = True,
) -> dict:
    """
    Navigate to OI Heatmap, click all 3 tabs, parse each response.

    Returns:
        {"oi": {...}, "oi_change": {...}, "volume": {...}}
    """
    url = build_url(product, "oi_heatmap", session.insid, session.qsid)
    results: dict = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        ctx     = await browser.new_context(storage_state=str(_SESSION_FILE))
        page    = await ctx.new_page()

        # Load page — don't capture initial response: server remembers last active tab,
        # so the initial tab is unpredictable (could be Volume, OI Change, etc.)
        print(f"  Loading {product}/oi_heatmap...")
        await safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
        await wait_for_updatepanel_idle(page, timeout=10.0)

        # Select "(All)" strikes so all strikes are visible for every tab.
        # Don't store this response — we don't know which tab is active yet.
        try:
            body = await expect_body(
                page, _is_oi_data,
                page.select_option(_STRIKES_DDL, value="-1", timeout=8000),
                body_check=lambda b: "grid-thm" in b,
                timeout=30.0,
            )
            if body:
                print(f"  Strikes set to (All)")
            await wait_for_updatepanel_idle(page, timeout=8.0)
        except Exception as e:
            print(f"  Could not set Strikes to All: {e}")

        # Click every tab explicitly — never rely on which tab happened to be
        # active on page load, since the server remembers the user's last tab.
        for tab_key, btn_id in TAB_BUTTONS.items():
            try:
                body = await expect_body(
                    page, _is_oi_data,
                    page.click(f"a[id*='{btn_id}']", timeout=8000),
                    body_check=lambda b: "grid-thm" in b,
                    timeout=60.0,
                )
                if body:
                    _store(results, body, product, tab_key)
                    print(f"    + {tab_key}")
                else:
                    print(f"    - {tab_key}: timeout")
                await wait_for_updatepanel_idle(page, timeout=8.0)
            except Exception as e:
                print(f"    - {tab_key}: {e}")

        await browser.close()

    print(f"  {len(results)}/3 tabs captured: {list(results)}")
    return results


def _store(results: dict, body: str, product: str, tab_key: str):
    try:
        data = parse_oi_heatmap_response(body, product, tab_key)
        results[tab_key] = data
        raw_path = _RAW_DIR / product / f"{tab_key}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(body, encoding="utf-8")
    except Exception as e:
        print(f"    parse error [{tab_key}]: {e}")
