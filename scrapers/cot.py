"""
COT (Commitments of Traders) fetcher — CFTC Disaggregated Futures-Only.

Data source: CFTC public download (free, no key)
  https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip
  Contains f_year.txt — CSV with header, all markets, all weeks for that year.

Market: GOLD - COMMODITY EXCHANGE INC  (code 088691)

Usage:
    python scrapers/cot.py           # fetch 2 years + save to dashboard/cot_data.js
"""

import csv
import io
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CFTC_BASE = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
GOLD_CODE = "088691"
YEARS     = 2  # download current + previous year for ~52 weeks

DASHBOARD_FILE = Path(__file__).parent.parent / "dashboard" / "cot_data.js"


def _int(row, key):
    try:
        return int(float((row.get(key) or "0").strip()))
    except (ValueError, TypeError):
        return 0


def _fetch_year(year: int) -> list:
    url = CFTC_BASE.format(year=year)
    print(f"    Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "TradingDashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    records = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        fname = next(n for n in z.namelist() if n.endswith(".txt"))
        with z.open(fname) as f:
            content = f.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                if (row.get("CFTC_Contract_Market_Code") or "").strip() != GOLD_CODE:
                    continue
                date = (row.get("Report_Date_as_YYYY-MM-DD") or "")[:10]
                if not date:
                    continue

                oi       = _int(row, "Open_Interest_All")
                mm_long  = _int(row, "M_Money_Positions_Long_All")
                mm_short = _int(row, "M_Money_Positions_Short_All")
                mm_spread= _int(row, "M_Money_Positions_Spread_All")
                pm_long  = _int(row, "Prod_Merc_Positions_Long_All")
                pm_short = _int(row, "Prod_Merc_Positions_Short_All")
                sw_long  = _int(row, "Swap_Positions_Long_All")
                sw_short = _int(row, "Swap__Positions_Short_All")

                records.append({
                    "date":      date,
                    "oi":        oi,
                    "mm_long":   mm_long,
                    "mm_short":  mm_short,
                    "mm_spread": mm_spread,
                    "mm_net":    mm_long - mm_short,
                    "mm_pct":    round((mm_long - mm_short) / oi * 100, 2) if oi else 0.0,
                    "pm_long":   pm_long,
                    "pm_short":  pm_short,
                    "pm_net":    pm_long - pm_short,
                    "sw_long":   sw_long,
                    "sw_short":  sw_short,
                    "sw_net":    sw_long - sw_short,
                    # week-over-week change (computed later)
                    "mm_chg_long":  _int(row, "Change_in_M_Money_Long_All"),
                    "mm_chg_short": _int(row, "Change_in_M_Money_Short_All"),
                })
    print(f"      {len(records)} Gold rows found")
    return records


def fetch() -> list:
    current_year = datetime.now().year
    all_records: dict = {}
    for offset in range(YEARS):
        year = current_year - offset
        try:
            rows = _fetch_year(year)
            for r in rows:
                all_records[r["date"]] = r
        except Exception as e:
            print(f"    Warning: year {year} failed — {e}")

    sorted_records = sorted(all_records.values(), key=lambda x: x["date"])
    return sorted_records


def save(records: list):
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "market":     "GOLD - COMEX (088691)",
        "report":     "Disaggregated Futures-Only COT",
        "source":     "CFTC (cftc.gov) — released weekly on Fridays",
        "records":    records,
    }
    js = "window.__COT_SNAPSHOT__ = " + json.dumps(payload, indent=2) + ";\n"
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.write_text(js)
    print(f"  COT saved → {DASHBOARD_FILE}")


def run():
    print("  Fetching COT data from CFTC...")
    records = fetch()
    if not records:
        print("  COT: no data returned")
        return

    latest = records[-1]
    prev   = records[-2] if len(records) > 1 else None

    mm_net_values = [r["mm_net"] for r in records]
    mm_52w_high   = max(mm_net_values)
    mm_52w_low    = min(mm_net_values)

    print(f"  Latest date : {latest['date']}")
    print(f"  MM net      : {latest['mm_net']:+,} ({latest['mm_pct']:+.1f}% of OI)")
    if prev:
        chg = latest["mm_net"] - prev["mm_net"]
        print(f"  WoW change  : {chg:+,}")
    print(f"  Range ({len(records)}w) : {mm_52w_low:+,} — {mm_52w_high:+,}")

    save(records)


if __name__ == "__main__":
    run()
