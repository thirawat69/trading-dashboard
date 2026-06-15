"""
Usage:
    python scrapers/run.py gold          # vol2vol only (default)
    python scrapers/run.py gold --oi     # oi_heatmap only
    python scrapers/run.py gold --cot        # COT only (no session needed)
    python scrapers/run.py gold --sentiment  # retail sentiment only (no session needed)
    python scrapers/run.py gold --all        # everything

    # Continuous loop — fetches gold + nasdaq vol2vol every N minutes (default 5)
    python scrapers/run.py --loop
    python scrapers/run.py --loop --interval=10
    python scrapers/run.py --loop --all         # include oi_heatmap + cot + sentiment each cycle

Flow (vol2vol):
    1. Load session
    2. Fetch all 5 Vol2Vol tabs
    3. contracts.upsert()
    4. vol2vol.save_snapshot()
    5. vol2vol.update_dashboard()

Flow (oi_heatmap):
    1. Load session
    2. Fetch all 3 OI Heatmap tabs (oi / oi_change / volume)
    3. oi_heatmap.save_snapshot()
    4. oi_heatmap.update_dashboard()
"""

import asyncio
import sys

import contracts
import vol2vol
import oi_heatmap
import cot
import sentiment
from session import Session, SessionExpiredError


async def run_vol2vol(product: str, session: Session, headless: bool):
    print(f"\n  [vol2vol]")
    all_tabs = await vol2vol.fetch_all_tabs(product, session, headless=headless)

    if not all_tabs:
        print("  No vol2vol data — check session or network")
        return

    first         = next(iter(all_tabs.values()))
    code          = first["expiration"]
    expiration_id = first["expiration_id"]
    dte           = first["dte"]

    print(f"  Contract  : {code}")
    print(f"  DTE       : {dte:.2f}")
    print(f"  Future    : {first['future_price']}")
    print(f"  ATM Vol   : {first['atm_vol']}%")

    contracts.upsert(product, code, expiration_id, dte)
    vol2vol.save_snapshot(product, code, all_tabs)
    vol2vol.update_dashboard(product, code, all_tabs)
    print(f"  Done — {len(all_tabs)} vol2vol tabs saved")


async def run_oi_heatmap(product: str, session: Session, headless: bool):
    print(f"\n  [oi_heatmap]")
    all_tabs = await oi_heatmap.fetch_all_tabs(product, session, headless=headless)

    if not all_tabs:
        print("  No oi_heatmap data — check session or network")
        return

    oi_heatmap.save_snapshot(product, all_tabs)
    oi_heatmap.update_dashboard(product, all_tabs)
    print(f"  Done — {len(all_tabs)} oi_heatmap tabs saved")


async def run(product: str, tool: str = "vol2vol", headless: bool = False):
    print(f"\nTrading Dashboard — {product.upper()} [{tool}]")
    print("=" * 45)

    # These don't need a session (public APIs)
    if tool == "cot":
        cot.run()
        return
    if tool == "sentiment":
        sentiment.run()
        return

    try:
        session = Session.load()
    except FileNotFoundError:
        print("Session not found. Run: python scrapers/session.py")
        return

    if not session.is_valid:
        print("Missing insid/qsid. Run: python scrapers/session.py")
        return

    print(f"  Session OK")

    if tool in ("vol2vol", "all"):
        await run_vol2vol(product, session, headless)
    if tool in ("oi_heatmap", "all"):
        await run_oi_heatmap(product, session, headless)
    if tool == "all":
        cot.run()
        sentiment.run()


LOOP_PRODUCTS = ["gold", "nasdaq"]


async def run_loop(tool: str = "vol2vol", interval_min: int = 5, headless: bool = False):
    """Fetch vol2vol (and optionally everything) for all products on a fixed interval."""
    print(f"\nLoop mode — products: {LOOP_PRODUCTS}, interval: {interval_min}m, tool: {tool}")
    iteration = 0
    while True:
        iteration += 1
        ts = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*50}")
        print(f"  Iteration {iteration}  [{ts}]")

        try:
            session = Session.load()
        except FileNotFoundError:
            print("  Session not found. Run: python scrapers/session.py")
            await asyncio.sleep(interval_min * 60)
            continue

        if not session.is_valid:
            print("  Missing insid/qsid. Run: python scrapers/session.py")
            await asyncio.sleep(interval_min * 60)
            continue

        try:
            for product in LOOP_PRODUCTS:
                if tool in ("vol2vol", "all"):
                    await run_vol2vol(product, session, headless)
                if tool in ("oi_heatmap", "all"):
                    await run_oi_heatmap(product, session, headless)

            if tool == "all":
                cot.run()
                sentiment.run()

        except SessionExpiredError as e:
            print(f"\n  ⚠  {e}")
            print("  Loop stopped — refresh session then restart.")
            return

        print(f"\n  Next run in {interval_min} min  (Ctrl-C to stop)")
        await asyncio.sleep(interval_min * 60)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--loop" in args:
        interval = int(next((a.split("=")[1] for a in args if a.startswith("--interval=")), "5"))
        tool = "all" if "--all" in args else "vol2vol"
        asyncio.run(run_loop(tool=tool, interval_min=interval))
    else:
        product = args[0] if args and not args[0].startswith("--") else "gold"
        if "--all" in args:
            tool = "all"
        elif "--oi" in args:
            tool = "oi_heatmap"
        elif "--cot" in args:
            tool = "cot"
        elif "--sentiment" in args:
            tool = "sentiment"
        else:
            tool = "vol2vol"
        try:
            asyncio.run(run(product, tool=tool))
        except SessionExpiredError as e:
            print(f"\n  ⚠  {e}")
            print("  Refresh session: python scrapers/session.py")
