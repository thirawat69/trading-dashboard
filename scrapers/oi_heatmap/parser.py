"""
OI Heatmap response parser.

Parses the HTML table from IntegratedVOIHeatMap UpdatePanel responses.

Response structure (ASP.NET UpdatePanel):
    length|updatePanel|upMain|<html content>|...

Table structure:
    thead row 1: empty | futures (colspan=2 each)
    thead row 2: "Strike" | expirations (colspan=2 each)
    thead row 3: up/dn | C | P  (repeated per expiration)
    tbody rows:  strike | call | put  (repeated per expiration)

Each data <td>:
    title = previous day EOD value (empty string if none)
    text  = current intraday value (empty if zero/no data)
"""

import re
from typing import Optional


def _extract_panel(body: str, panel_id: str) -> Optional[str]:
    m = re.search(rf'(\d+)\|updatePanel\|{re.escape(panel_id)}\|', body)
    if not m:
        return None
    length = int(m.group(1))
    return body[m.end():m.end() + length]


def _parse_int(text: str) -> Optional[int]:
    clean = re.sub(r'<[^>]+>', '', text).strip().replace(',', '')
    if not clean:
        return None
    try:
        return int(clean)
    except ValueError:
        return None


def _parse_float(text: str) -> Optional[float]:
    clean = re.sub(r'<[^>]+>', '', text).strip().replace(',', '')
    if not clean:
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def _parse_expirations(thead_html: str) -> list:
    """Extract expiration and underlying future info from thead."""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', thead_html, re.DOTALL)
    if len(rows) < 2:
        return []

    def _th_cells(row_html: str) -> list:
        return re.findall(r'<th[^>]*colspan=["\']?2["\']?[^>]*>(.*?)</th>', row_html, re.DOTALL)

    def _first_caps(html: str) -> Optional[str]:
        m = re.search(r'>([A-Z][A-Z0-9]{1,9})<', html)
        return m.group(1) if m else None

    def _first_price(html: str) -> Optional[float]:
        for m in re.finditer(r'>([0-9]{1,6}(?:[,.][0-9]+)?)<', html):
            v = m.group(1).replace(',', '')
            if '.' in v or len(v) >= 4:
                try:
                    return float(v)
                except ValueError:
                    pass
        return None

    def _first_dte(html: str) -> Optional[int]:
        nums = re.findall(r'<span[^>]*>(\d{1,4})</span>', html)
        if nums:
            return int(nums[-1])
        return None

    futures = []
    for th in _th_cells(rows[0]):
        sym = _first_caps(th)
        if sym and len(sym) >= 3:
            futures.append({"symbol": sym, "price": _first_price(th)})

    expirations = []
    fut_idx = 0
    for th in _th_cells(rows[1]):
        sym = _first_caps(th)
        if not sym or len(sym) < 3:
            continue
        exp_m = re.search(r'[Ee]xpires?:\s*([^"\'<]+)', th)
        exp_date = exp_m.group(1).strip() if exp_m else None

        fut = futures[fut_idx] if fut_idx < len(futures) else {}
        fut_idx += 1
        expirations.append({
            "symbol":        sym,
            "dte":           _first_dte(th),
            "expiry_date":   exp_date,
            "future_symbol": fut.get("symbol"),
            "future_price":  fut.get("price"),
        })

    return expirations


def _title_val(attrs: str) -> Optional[int]:
    m = re.search(r"title=['\"]([^'\"]*)['\"]", attrs)
    return _parse_int(m.group(1)) if m else None


def _parse_strikes(tbody_html: str, expirations: list) -> list:
    """Parse tbody rows into per-strike call/put OI data."""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_html, re.DOTALL)
    strikes = []

    for row in rows:
        strike_td_m = re.search(
            r'<td([^>]+colspan=["\']2["\'][^>]*)>(.*?)</td>', row, re.DOTALL
        )
        if not strike_td_m:
            continue

        strike_val = _parse_float(strike_td_m.group(2))
        if strike_val is None:
            continue

        is_atm = 'atm' in strike_td_m.group(1)

        number_cells = re.findall(
            r'<td([^>]*class=["\'][^"\']*number[^"\']*["\'][^>]*)>(.*?)</td>',
            row, re.DOTALL
        )

        cells: dict = {}
        for i, exp in enumerate(expirations):
            call_attrs, call_content = number_cells[i * 2] if i * 2 < len(number_cells) else ("", "")
            put_attrs, put_content   = number_cells[i * 2 + 1] if i * 2 + 1 < len(number_cells) else ("", "")

            cells[exp["symbol"]] = {
                "call":      _parse_int(call_content),
                "put":       _parse_int(put_content),
                "call_prev": _title_val(call_attrs),
                "put_prev":  _title_val(put_attrs),
            }

        strikes.append({
            "strike":  strike_val,
            "is_atm":  is_atm,
            "cells":   cells,
        })

    return strikes


def parse_oi_heatmap_response(body: str, product: str, tab: str = "oi") -> dict:
    """
    Parse an IntegratedVOIHeatMap UpdatePanel response.

    Returns:
        {
            "product": str,
            "tab": str,                  # "oi" | "oi_change" | "volume"
            "expirations": [...],
            "atm_strike": float | None,
            "strikes": [
                {
                    "strike": float,
                    "is_atm": bool,
                    "cells": {
                        "<expiry>": {
                            "call": int | None,
                            "put": int | None,
                            "call_prev": int | None,
                            "put_prev": int | None,
                        }
                    }
                }
            ]
        }
    """
    content = _extract_panel(body, "upMain")
    if not content:
        raise ValueError("upMain panel not found")

    table_m = re.search(
        r'<table[^>]*class=["\'][^"\']*grid-thm[^"\']*["\'][^>]*>(.*?)</table>',
        content, re.DOTALL
    )
    if not table_m:
        raise ValueError("OI matrix table not found")

    table_html = table_m.group(0)

    thead_m = re.search(r'<thead>(.*?)</thead>', table_html, re.DOTALL)
    tbody_m = re.search(r'<tbody>(.*?)</tbody>', table_html, re.DOTALL)
    if not thead_m or not tbody_m:
        raise ValueError("thead/tbody not found")

    expirations = _parse_expirations(thead_m.group(1))
    strikes     = _parse_strikes(tbody_m.group(1), expirations)
    atm_strike  = next((s["strike"] for s in strikes if s["is_atm"]), None)

    return {
        "product":     product,
        "tab":         tab,
        "expirations": expirations,
        "atm_strike":  atm_strike,
        "strikes":     strikes,
    }
