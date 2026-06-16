"""
Vol2Vol dashboard writer.

update_dashboard(product, contract, all_tabs)
"""

import json
import re
from datetime import datetime
from pathlib import Path

DASHBOARD_DATA = Path(__file__).parent.parent.parent / "dashboard" / "data.js"
SNAPSHOTS_DIR  = Path(__file__).parent.parent.parent / "data" / "snapshots" / "vol2vol"


def update_dashboard(product: str, contract: str, all_tabs: dict):
    """Write dashboard/data.js — includes all of today's snapshots as an array."""
    existing = {}
    if DASHBOARD_DATA.exists():
        text = DASHBOARD_DATA.read_text(encoding="utf-8")
        m = re.match(r"window\.__SNAPSHOT__\s*=\s*(.+?);?\s*$", text, re.DOTALL)
        if m:
            try:
                existing = json.loads(m.group(1))
                if "tabs" in existing:   # migrate old single-product root format
                    existing = {}
                # drop stale product entry that still uses old per-product format
                if product in existing and "tabs" in existing.get(product, {}):
                    del existing[product]
            except Exception:
                pass

    existing[product] = {
        "contract":  contract,
        "snapshots": _load_today_snapshots(product, contract),
    }
    DASHBOARD_DATA.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA.write_text(
        "window.__SNAPSHOT__ = " + json.dumps(existing, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    print(f"  Dashboard data updated -> dashboard/data.js [{product}]")


def _load_today_snapshots(product: str, contract: str) -> list:
    """Return all of today's snapshot objects sorted by time."""
    snap_dir = SNAPSHOTS_DIR / product / contract
    today    = datetime.now().strftime("%Y-%m-%d")
    result   = []
    for f in sorted(snap_dir.glob(f"{today}T*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({"fetched_at": data["fetched_at"], "tabs": data["tabs"]})
        except Exception:
            pass
    return result
