"""
Retail sentiment fetcher — fxssi.com Current Ratio tool.

Data source: https://fxssi.com/api/current-ratios  (public, no auth)
Returns Buy% per broker per symbol + weighted average.
Updates every ~10 minutes.

Usage:
    python scrapers/sentiment.py        # fetch + save to dashboard/sentiment_data.js
"""

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL      = "https://fxssi.com/api/current-ratios"
SYMBOLS      = ["XAUUSD", "NAS100"]
DASHBOARD_FILE = Path(__file__).parent.parent / "dashboard" / "sentiment_data.js"


def fetch() -> dict:
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "TradingDashboard/1.0", "Referer": "https://fxssi.com/"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data


def process(raw: dict) -> dict:
    titles  = raw.get("broker_titles", {})
    weights = raw.get("broker_weights", {})
    pairs   = raw.get("pairs", {})
    formed  = raw.get("formed", 0)

    result = {}
    for sym in SYMBOLS:
        pair_data = pairs.get(sym, {})
        if not pair_data:
            continue

        brokers = []
        for code, buy_str in pair_data.items():
            if code in ("average", "oip"):
                continue
            buy = float(buy_str)
            brokers.append({
                "code":   code,
                "name":   titles.get(code, code.upper()),
                "buy":    round(buy, 2),
                "sell":   round(100 - buy, 2),
                "weight": weights.get(code, 1),
            })
        brokers.sort(key=lambda x: -x["weight"])  # heaviest first

        avg_buy = float(pair_data.get("average", 0))
        result[sym] = {
            "symbol":  sym,
            "brokers": brokers,
            "average": {"buy": round(avg_buy, 2), "sell": round(100 - avg_buy, 2)},
        }

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "formed_at":  formed,
        "source":     "fxssi.com Current Ratio",
        "symbols":    result,
    }


def save(payload: dict):
    js = "window.__SENTIMENT__ = " + json.dumps(payload, indent=2) + ";\n"
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.write_text(js)
    print(f"  Sentiment saved → {DASHBOARD_FILE}")


def run():
    print("  Fetching sentiment from fxssi.com...")
    raw = fetch()
    payload = process(raw)
    for sym, d in payload["symbols"].items():
        avg = d["average"]["buy"]
        n   = len(d["brokers"])
        print(f"  {sym}: {avg:.1f}% buy (avg of {n} brokers)")
    save(payload)


if __name__ == "__main__":
    run()
