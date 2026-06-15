"""
Vol2Vol snapshot storage.

save_snapshot(product, contract, all_tabs) → Path
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

SNAPSHOTS_DIR = Path(__file__).parent.parent.parent / "data" / "snapshots" / "vol2vol"


def save_snapshot(product: str, contract: str, all_tabs: dict) -> Path:
    """Save all tabs as one timestamped JSON. Skip if data is identical."""
    latest = _latest_snapshot(product, contract)
    if latest:
        prev = json.loads(latest.read_text())
        if _content_hash(prev.get("tabs", {})) == _content_hash(all_tabs):
            print(f"  Data unchanged — skipping snapshot")
            return latest

    snap_dir = SNAPSHOTS_DIR / product / contract
    snap_dir.mkdir(parents=True, exist_ok=True)

    ts  = datetime.now()
    out = snap_dir / (ts.strftime("%Y-%m-%dT%H%M%S") + ".json")
    out.write_text(
        json.dumps(
            {
                "product":    product,
                "contract":   contract,
                "fetched_at": ts.isoformat(),
                "tabs":       all_tabs,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  Saved: {out.relative_to(snap_dir.parent.parent.parent.parent)}")
    return out


def _latest_snapshot(product: str, contract: str) -> Optional[Path]:
    snap_dir = SNAPSHOTS_DIR / product / contract
    if not snap_dir.exists():
        return None
    files = sorted(snap_dir.glob("*.json"))
    return files[-1] if files else None


def _strip_timestamps(obj):
    if isinstance(obj, dict):
        return {k: _strip_timestamps(v) for k, v in obj.items() if k != "fetched_at"}
    if isinstance(obj, list):
        return [_strip_timestamps(i) for i in obj]
    return obj


def _content_hash(tabs: dict) -> str:
    normalized = json.dumps(_strip_timestamps(tabs), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode()).hexdigest()
