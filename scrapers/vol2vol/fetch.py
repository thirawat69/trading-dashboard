"""
Vol2Vol Playwright fetcher.

fetch_all_tabs(product, session, headless) → dict
"""

from pathlib import Path

from playwright.async_api import async_playwright

from session import Session
from url_builder import build_url
from playwright_utils import safe_goto, expect_body, wait_for_updatepanel_idle
from .parser import parse_vol2vol_response, vol2vol_to_dict

_SESSION_FILE = Path(__file__).parent.parent.parent / "data" / "session.json"
_RAW_DIR      = Path(__file__).parent.parent.parent / "data" / "raw" / "vol2vol"

VALUE_NAME_MAP = {
    "Intraday Volume":      "intraday",
    "EOD Volume":           "eod",
    "Open Interest":        "oi",
    "Open Interest Change": "oi_change",
    "Churn":                "churn",
}

TAB_BUTTONS = {
    "intraday":  "lbIntradayVolume",
    "eod":       "lbEODVolume",
    "oi":        "lbOI",
    "oi_change": "lbOIChg",
    "churn":     "lbChurn",
}


def _is_vv_data(r):
    """Match the AJAX POST responses that carry JSONSettings chart data."""
    return (
        "QuikStrikeView.aspx" in r.url
        and "IntegratedV2VExpectedRange" in r.url
        and r.request.method == "POST"
        and r.status == 200
    )


async def fetch_all_tabs(
    product: str,
    session: Session,
    headless: bool = True,
) -> dict:
    """
    Navigate to Vol2Vol, click all 5 tabs, parse each response.

    Returns:
        {"intraday": {...}, "eod": {...}, "oi": {...}, "oi_change": {...}, "churn": {...}}
    """
    url = build_url(product, "vol2vol", session.insid, session.qsid)
    results: dict = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        ctx     = await browser.new_context(storage_state=str(_SESSION_FILE))
        page    = await ctx.new_page()

        # Load page — don't capture initial response: server remembers last active tab,
        # so the initial tab is unpredictable.
        print(f"  Loading {product}/vol2vol...")
        await safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
        await wait_for_updatepanel_idle(page, timeout=10.0)

        # Click every tab explicitly — never rely on which tab happened to be
        # active on page load, since the server remembers the user's last tab.
        for tab_key, btn_id in TAB_BUTTONS.items():
            try:
                body = await expect_body(
                    page, _is_vv_data,
                    page.click(f"a[id*='{btn_id}']", timeout=8000),
                    body_check=lambda b: "JSONSettings" in b,
                    timeout=60.0,
                )
                if body:
                    _store(results, body, product)
                    print(f"    + {tab_key}")
                else:
                    print(f"    - {tab_key}: timeout")
                await wait_for_updatepanel_idle(page, timeout=8.0)
            except Exception as e:
                print(f"    - {tab_key}: {e}")

        await browser.close()

    print(f"  {len(results)}/5 tabs captured: {list(results)}")
    return results


def _store(results: dict, body: str, product: str):
    try:
        data = parse_vol2vol_response(body, product)
        key = VALUE_NAME_MAP.get(
            data.value_name,
            data.value_name.lower().replace(" ", "_"),
        )
        results[key] = vol2vol_to_dict(data)
        raw_path = _RAW_DIR / product / f"{key}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(body, encoding="utf-8")
    except Exception as e:
        print(f"    parse error: {e}")
