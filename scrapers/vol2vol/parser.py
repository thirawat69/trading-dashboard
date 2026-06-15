"""
Parser สำหรับ QuikStrike Vol2Vol Expected Range tool
แปลง ASP.NET UpdatePanel response → structured dict

ข้อมูลที่ดึงออกมา:
- metadata: product, expiration, future price, ATM vol, DTE
- ranges: expected price ranges 3 ระดับ (±1σ, ±2σ, ±3σ)
- delta_levels: strike prices ของ 5Δ, 15Δ, 25Δ, 35Δ, 45Δ (call & put)
- strikes: Call/Put data per strike (volume, OI, OI change, churn)
- subtitle_stats: Put total, Call total, Vol Chg, Future Chg
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ExpectedRange:
    level: int
    lower: float
    upper: float
    lower_width: float
    upper_width: float
    color: str


@dataclass
class DeltaLevel:
    label: str
    strike: float
    side: str
    delta: int


@dataclass
class StrikeData:
    strike: float
    call_value: float
    put_value: float
    call_strike_id: Optional[int] = None
    put_strike_id: Optional[int] = None
    vol: Optional[float] = None
    vol_settle: Optional[float] = None


@dataclass
class SubtitleStats:
    put_total: Optional[float] = None
    call_total: Optional[float] = None
    vol: Optional[float] = None
    vol_chg: Optional[float] = None
    future_chg: Optional[float] = None


@dataclass
class Vol2VolData:
    fetched_at: str
    product: str
    expiration: str
    expiration_id: int
    dte: float
    future_price: float
    atm_vol: float
    value_name: str
    title: str
    ranges: list
    delta_levels: list
    strikes: list
    stats: SubtitleStats = field(default_factory=SubtitleStats)


# ── Extraction helpers ────────────────────────────────────────────────────────

def extract_json_settings(response_body: str) -> dict:
    pattern = r'"JSONSettings"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}'
    match = re.search(pattern, response_body, re.DOTALL)
    if not match:
        raise ValueError("JSONSettings not found in response")
    raw = match.group(1)
    json_str = raw.encode('utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8')
    return json.loads(json_str)


def parse_subtitle(subtitle_html: str) -> SubtitleStats:
    stats = SubtitleStats()
    text = re.sub(r'<[^>]+>', '', subtitle_html)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace(',', '')

    m = re.search(r'Put:\s*([\d.+-]+)', text)
    if m: stats.put_total = float(m.group(1))
    m = re.search(r'Call:\s*([\d.+-]+)', text)
    if m: stats.call_total = float(m.group(1))
    m = re.search(r'Vol:\s*([\d.]+)', text)
    if m: stats.vol = float(m.group(1))
    m = re.search(r'Vol Chg:\s*([+-]?[\d.]+)', text)
    if m: stats.vol_chg = float(m.group(1))
    m = re.search(r'Future Chg:\s*([+-]?[\d.]+)', text)
    if m: stats.future_chg = float(m.group(1))

    return stats


def parse_ranges(ranges_data: dict) -> list:
    data = ranges_data.get("data", [])
    levels = {}
    for item in data:
        lvl = item["Tag"]["Range"]
        width = float(item["dataLabels"]["format"])
        if lvl not in levels:
            levels[lvl] = []
        levels[lvl].append({
            "x": item["x"], "x2": item["x2"],
            "width": width, "color": item.get("color", ""),
        })

    result = []
    for lvl in sorted(levels.keys()):
        segs = sorted(levels[lvl], key=lambda s: s["x"])
        lower       = segs[0]["x"]
        upper       = segs[1]["x2"]
        lower_width = segs[0]["width"]
        upper_width = segs[1]["width"]
        color       = segs[1].get("color", "")
        result.append(ExpectedRange(
            level=lvl,
            lower=round(lower, 2), upper=round(upper, 2),
            lower_width=lower_width, upper_width=upper_width,
            color=color,
        ))
    return result


def parse_delta_levels(plotlines: list) -> list:
    result = []
    delta_pattern = re.compile(r'(\d+)Δ([CP])')
    for pl in plotlines:
        label_text = pl.get("label", {}).get("text", "")
        m = delta_pattern.match(label_text)
        if not m:
            continue
        result.append(DeltaLevel(
            label=label_text,
            strike=round(pl["value"], 2),
            side="put" if m.group(2) == "P" else "call",
            delta=int(m.group(1)),
        ))
    result.sort(key=lambda d: (0 if d.side == "put" else 1, d.delta))
    return result


def parse_strike_data(call_series: dict, put_series: dict,
                      vol_series: dict = None, vol_settle_series: dict = None) -> list:
    call_map       = {item["x"]: item        for item in call_series.get("data", [])}
    put_map        = {item["x"]: item        for item in put_series.get("data", [])}
    vol_map        = {item["x"]: item.get("y") for item in (vol_series        or {}).get("data", [])}
    vol_settle_map = {item["x"]: item.get("y") for item in (vol_settle_series or {}).get("data", [])}
    all_strikes = sorted(set(list(call_map.keys()) + list(put_map.keys())))
    result = []
    for strike in all_strikes:
        c = call_map.get(strike, {})
        p = put_map.get(strike, {})
        result.append(StrikeData(
            strike=strike,
            call_value=c.get("y", 0.0),
            put_value=p.get("y", 0.0),
            call_strike_id=c.get("Tag", {}).get("StrikeId"),
            put_strike_id=p.get("Tag", {}).get("StrikeId"),
            vol=vol_map.get(strike),
            vol_settle=vol_settle_map.get(strike),
        ))
    return result


def parse_title(title: str) -> tuple:
    parts = title.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (title, "")


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_vol2vol_response(response_body: str, product_name: str = "") -> Vol2VolData:
    settings = extract_json_settings(response_body)
    expiration, tab_name = parse_title(settings.get("Title", ""))
    stats = parse_subtitle(settings.get("Subtitle", ""))

    return Vol2VolData(
        fetched_at=datetime.now().isoformat(),
        product=settings.get("Product", {}).get("Name", product_name),
        expiration=expiration,
        expiration_id=settings.get("ExpirationId", 0),
        dte=round(settings.get("DTE", 0), 4),
        future_price=settings.get("FuturePrice", 0.0),
        atm_vol=round(settings.get("ATMVol", 0) * 100, 2),
        value_name=settings.get("ValueName", ""),
        title=settings.get("Title", ""),
        ranges=parse_ranges(settings.get("Ranges", {})),
        delta_levels=parse_delta_levels(settings.get("PlotLines", [])),
        strikes=parse_strike_data(settings.get("Call", {}), settings.get("Put", {}),
                                  settings.get("Vol", {}), settings.get("VolSettle", {})),
        stats=stats,
    )


def vol2vol_to_dict(data: Vol2VolData) -> dict:
    return asdict(data)
