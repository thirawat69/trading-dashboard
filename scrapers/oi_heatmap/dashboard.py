"""
OI Heatmap dashboard writer.

update_dashboard(product, all_tabs)
"""

import json
import re
from datetime import datetime
from pathlib import Path

DASHBOARD_DATA = Path(__file__).parent.parent.parent / "dashboard" / "oi_data.js"


def update_dashboard(product: str, all_tabs: dict):
    """Write dashboard/oi_data.js (multi-product: merges, does not overwrite other products)."""
    existing = {}
    if DASHBOARD_DATA.exists():
        text = DASHBOARD_DATA.read_text(encoding="utf-8")
        m = re.match(r"window\.__OI_SNAPSHOT__\s*=\s*(.+?);?\s*$", text, re.DOTALL)
        if m:
            try:
                existing = json.loads(m.group(1))
                # migrate old single-product format (had top-level "tabs" key)
                if "tabs" in existing:
                    existing = {}
            except Exception:
                pass

    existing[product] = {
        "product":    product,
        "fetched_at": datetime.now().isoformat(),
        "tabs":       all_tabs,
    }
    DASHBOARD_DATA.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA.write_text(
        "window.__OI_SNAPSHOT__ = " + json.dumps(existing, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    print(f"  Dashboard data updated -> dashboard/oi_data.js [{product}]")
