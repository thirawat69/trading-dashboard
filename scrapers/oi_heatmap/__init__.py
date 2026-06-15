"""
OI Heatmap package — IntegratedVOIHeatMap data pipeline.

Public API (same interface as the old oi_heatmap.py):
    fetch_all_tabs(product, session, headless) → dict
    save_snapshot(product, all_tabs) → Path
    update_dashboard(product, all_tabs)
"""

from .fetch import fetch_all_tabs
from .snapshot import save_snapshot
from .dashboard import update_dashboard

__all__ = ["fetch_all_tabs", "save_snapshot", "update_dashboard"]
