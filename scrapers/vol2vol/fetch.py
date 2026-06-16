"""
Vol2Vol Playwright fetcher.

fetch_all_tabs(product, session, headless) → dict

Sequence inside fetch_all_tabs:
  1. safe_goto  — load page (no capture: server remembers last active tab)
  2. wait_for_updatepanel_idle
  3. _select_nearest_contract — parse DTE from lbExpiration title attrs,
       click the one with the smallest DTE > 0 (skip if already selected)
  4. wait_for_updatepanel_idle  (inside _select_nearest_contract)
  5. loop over TAB_BUTTONS (intraday / eod / oi / oi_change / churn):
       click tab → expect_body → _store → wait_for_updatepanel_idle
"""

import re
from pathlib import Path
from typing import Optional

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


async def _select_nearest_contract(page) -> Optional[str]:
    """
    Find the contract link with the smallest positive DTE and click it.
    Skips the click if it's already selected (avoids a free UpdatePanel round-trip).
    Returns the option symbol that ended up selected, or None if nothing found.
    """
    links = await page.query_selector_all("a[id*='lbExpiration']")
    if not links:
        return None

    best_el, best_dte, best_sym = None, float("inf"), None
    for el in links:
        title = await el.get_attribute("title") or ""
        dte_m = re.search(r"\((\d+\.?\d*) DTE\)", title)
        sym_m = re.search(r"Option Symbol:\s+(\S+)", title)
        if dte_m:
            dte = float(dte_m.group(1))
            if 0 < dte < best_dte:
                best_dte = dte
                best_el = el
                best_sym = sym_m.group(1) if sym_m else None

    if not best_el:
        return None

    cls = await best_el.get_attribute("class") or ""
    if "selected" in cls:
        print(f"    contract: {best_sym} ({best_dte:.2f} DTE) — already selected")
        return best_sym

    print(f"    selecting contract: {best_sym} ({best_dte:.2f} DTE)")
    # JS click bypasses Playwright's visibility check — the link may be
    # off-screen in a scrollable nav but still reachable via __doPostBack.
    await page.evaluate("el => el.click()", best_el)
    await wait_for_updatepanel_idle(page, timeout=15.0)
    return best_sym


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

        # Explicitly select the contract with the smallest DTE so we always
        # fetch the front-month regardless of the server's remembered session state.
        await _select_nearest_contract(page)

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
