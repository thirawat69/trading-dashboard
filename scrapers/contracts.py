"""
Contract/expiration store — one JSON file per product

data/contracts/{product}.json:
{
  "product": "gold",
  "last_updated": "2026-06-13T10:30:00",
  "contracts": [
    {
      "code":          "G2RM6",
      "expiration_id": 12345,
      "dte":           2.5,          ← updated every fetch
      "first_seen":    "...",
      "dte_updated":   "..."         ← timestamp of last DTE update
    }
  ]
}

Rules:
  - New contract → insert full record
  - Existing contract → update dte + dte_updated only
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

CONTRACTS_DIR = Path(__file__).parent.parent / "data" / "contracts"
CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)


def _path(product: str) -> Path:
    return CONTRACTS_DIR / f"{product}.json"


def load(product: str) -> dict:
    f = _path(product)
    return json.loads(f.read_text()) if f.exists() else {"product": product, "contracts": []}


def upsert(product: str, code: str, expiration_id: int, dte: float) -> dict:
    """Add new contract or update DTE only if it already exists."""
    store = load(product)
    now = datetime.now().isoformat()

    existing = next((c for c in store["contracts"] if c["code"] == code), None)
    if existing:
        existing["dte"] = round(dte, 4)
        existing["dte_updated"] = now
    else:
        store["contracts"].append({
            "code": code,
            "expiration_id": expiration_id,
            "dte": round(dte, 4),
            "first_seen": now,
            "dte_updated": now,
        })
        print(f"  📋 New contract discovered: {code} ({dte:.1f} DTE)")

    store["last_updated"] = now
    _path(product).write_text(json.dumps(store, indent=2))
    return store


def get_nearest(product: str) -> Optional[dict]:
    """Return contract with the smallest positive DTE."""
    valid = [c for c in load(product)["contracts"] if c.get("dte", 0) > 0]
    return min(valid, key=lambda c: c["dte"]) if valid else None


def list_all(product: str) -> list[dict]:
    return load(product).get("contracts", [])
