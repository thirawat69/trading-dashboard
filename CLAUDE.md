# Trading Dashboard — Project Summary

## What This Is

A single-page trading analytics dashboard for CME commodity/equity options (Gold, Nasdaq).
Python scrapers pull data from QuikStrike (CME, authenticated) + CFTC + fxssi.com, write it as JS globals, and a vanilla HTML/Chart.js frontend reads them statically.

**No framework, no build step, no database.**

---

## Architecture in One Line

```
Python scrapers → write JS data files → static HTML dashboard reads them
```

---

## Directory Layout

```
trading-dashboard/
├── dashboard/          # Frontend (serve with: python3 -m http.server 8765)
│   ├── index.html      # Entire UI — ~1200 lines of vanilla JS + CSS
│   ├── data.js         # Vol2Vol snapshot  → window.__SNAPSHOT__
│   ├── oi_data.js      # OI Heatmap        → window.__OI_SNAPSHOT__
│   ├── cot_data.js     # COT data          → window.__COT_SNAPSHOT__
│   ├── sentiment_data.js # Sentiment       → window.__SENTIMENT__
│   └── oi_chart_data.js
├── scrapers/           # Python backend — one package per data source
│   ├── run.py          # CLI orchestrator (entry point)
│   ├── session.py      # CME login → captures insid/qsid tokens
│   ├── contracts.py    # Tracks active contracts + DTE per product
│   ├── cot.py          # CFTC public download
│   ├── sentiment.py    # fxssi.com API
│   ├── url_builder.py  # Builds QuikStrike URLs
│   ├── vol2vol/        # Vol2Vol Expected Range module
│   └── oi_heatmap/     # OI Heatmap module
├── data/               # Persisted state (JSON files, not a DB)
│   ├── session.json    # CME tokens {insid, qsid}
│   ├── contracts/      # gold.json, nasdaq.json
│   ├── snapshots/      # Time-series raw snapshots (grows unbounded)
│   └── raw/            # Debug: raw API responses
├── notebooks/          # Jupyter exploration
├── .env                # CME_EMAIL, CME_PASSWORD
└── .claude/launch.json # Dev server config
```

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Vanilla HTML/CSS/JS, Chart.js 4.4.4, chartjs-plugin-annotation |
| Backend | Python 3.9+, Playwright (async), urllib, python-dotenv |
| Data | Static JS files (no API server, no database) |
| Dev server | `python3 -m http.server 8765` |

---

## Data Sources

| Source | Auth | Data | Frequency |
|--------|------|------|-----------|
| CME QuikStrike | Cookie session (insid + qsid) | Vol2Vol, OI Heatmap | On-demand |
| CFTC | Public | COT Disaggregated Futures-Only | Weekly (Friday) |
| fxssi.com | Public | Retail sentiment % buy/sell per broker | ~10 min |

**QuikStrike products:** Gold (pid=40), Nasdaq (pid=121)
**QuikStrike tools:** `IntegratedV2VExpectedRange`, `IntegratedVOIHeatMap`
**COT identifier:** CFTC market code `088691` = Gold COMEX

---

## Dashboard Views (4 tabs)

| View | Data file | Key display |
|------|-----------|-------------|
| Vol2Vol | data.js | Stacked bar (Put/Call by strike) + IV line, 5 sub-tabs |
| OI Heatmap | oi_data.js | HTML table: strikes × expirations, color-coded |
| COT | cot_data.js | MM/PM/SW net positioning line chart, 2-year rolling |
| Sentiment | sentiment_data.js | Broker buy% bars, bias meter |

Vol2Vol sub-tabs: Intraday Volume, EOD Volume, Open Interest, OI Change, Churn
OI Heatmap sub-tabs: Open Interest, OI Change, Volume

---

## Key Data Models (Python dataclasses)

```python
# Vol2Vol
Vol2VolData:
  fetched_at, product, expiration, expiration_id, dte
  future_price, atm_vol
  ranges: list[ExpectedRange]   # ±1σ/2σ/3σ
  delta_levels: list[DeltaLevel] # 5Δ–45Δ strikes
  strikes: list[StrikeData]     # call_value, put_value, vol per strike
  stats: SubtitleStats

# OI Heatmap
OIHeatmapData:
  expirations: [{symbol, dte, future_price}]
  strikes: [{strike, cells: [{expiry, call_oi, put_oi}]}]
  atm_strike

# COT row: date, mm_long/short/net, pm_long/short/net, sw_long/short/net
# Sentiment: symbol, brokers: [{code, name, buy%, sell%, weight}]
```

---

## Frontend State (JS globals in index.html)

```js
SNAP     = window.__SNAPSHOT__       // Vol2Vol
OI_SNAP  = window.__OI_SNAPSHOT__    // OI Heatmap
COT      = window.__COT_SNAPSHOT__   // COT
SENT     = window.__SENTIMENT__      // Sentiment

// UI state: PRODUCT, VIEW, VV_TAB, OI_TAB, SNAP_IDX, axisFlipped
// Key functions: switchProduct(), switchView(), drawChart(), renderHeatmap(),
//                renderCOTChart(), renderSentiment(), renderTimeline()
```

**`window.__SNAPSHOT__` format** (written by `scrapers/vol2vol/dashboard.py`):
```js
{
  gold: {
    contract: "G3TM6",
    snapshots: [                          // all fetches for today, sorted ascending
      { fetched_at: "2026-06-16T11:19:52", tabs: { intraday: {...}, eod: {...}, ... } },
      { fetched_at: "2026-06-16T12:28:43", tabs: { ... } },
      ...
    ]
  },
  nasdaq: { contract: "...", snapshots: [...] }
}
```
`SNAP_IDX` = -1 means latest snapshot; 0..n-1 pins a historical one.
The frontend timeline scrubber (inside `#vv-timeline`) lets the user browse snapshots.

Data shape is `{gold: {...}, nasdaq: {...}}` — single toggle switches products without reload.

---

## CME Authentication Flow

1. Run `python scrapers/session.py` — headless Playwright browser logs into QuikStrike
2. Captures `insid` + `qsid` from AJAX request URL
3. Saves to `data/session.json` — valid for 24+ hours
4. All subsequent scraper calls load these tokens from file

If scraping fails with auth errors → re-run `session.py`.

---

## Common Commands

```bash
# Auth (one-time, or when session expires)
python scrapers/session.py

# Fetch data
python scrapers/run.py gold               # Vol2Vol
python scrapers/run.py gold --oi          # OI Heatmap
python scrapers/run.py gold --cot --sentiment  # COT + sentiment
python scrapers/run.py nasdaq             # Nasdaq Vol2Vol

# Continuous loop
python scrapers/run.py --loop --all --interval=5  # every 5 min

# Serve dashboard
python3 -m http.server 8765
# → http://localhost:8765/dashboard/index.html
```

---

## Scraper Pipeline (per module)

```
fetch.py → parser.py → snapshot.py → dashboard.py (writes JS file)
```

Each module is self-contained. `run.py` orchestrates them.
`snapshot.py` saves timestamped JSON to `data/snapshots/` for historical analysis.

---

## Trading Philosophy & Dashboard Intent

This dashboard is built around two distinct time horizons:

### Vol2Vol → 0DTE / Intraday (<1 DTE)
Primary use: **day trading Gold options** on expiration day or the day before.

Key concepts that matter here:
- **Gamma** — near-expiry ATM options have extremely high gamma; Delta changes rapidly with price
- **Gamma hedging (dealer hedging)** — market makers who sold options must delta-hedge continuously. If dealers are net short gamma (sold calls + puts), they BUY when price rises and SELL when price falls (pro-cyclical, amplifies moves). If net long gamma, they trade against the move (dampening).
- **0DTE gamma squeeze** — on expiration day, gamma is highest; large prints at key strikes force rapid dealer rebalancing → can cause sharp, fast price moves
- **GEX (Gamma Exposure)** = Open Interest × Gamma × contract size. Positive GEX = dealers are long gamma (market maker = stabiliser). Negative GEX = dealers are short gamma (market maker = amplifier).
- **Flip level** — strike where net GEX crosses zero. Below the flip = dealers amplify moves; above = they dampen. A common intraday trigger zone.

What to look for in Vol2Vol for 0DTE:
- Which strikes have the largest OI (potential gamma pin or magnet)
- OI Change (new positions opened today vs yesterday) — fresh 0DTE prints
- Intraday Volume — where the action is happening right now
- ATM IV and expected range (±1σ) — defines the "fair" daily move
- Call Wall / Put Wall from the sidebar — strikes where dealer gamma flips

### OI Heatmap → Big Picture (Multi-expiry Positioning)
Primary use: **understanding where large institutional positions are parked** across all expirations.

Key concepts:
- Large OI clusters at specific strikes = support/resistance levels that may act as magnets or walls
- OI Change across expirations shows which strikes are being built vs unwound
- Put/Call ratio by expiry reveals directional bias per time horizon
- Max Pain = strike where total option buyer losses are maximised (some believe price gravitates here near expiry)
- Strikes ↑ vs Strikes ↓ (from OI Change tab) = breadth of positioning shifts — a broad increase in OI is more meaningful than a spike at one strike

---

## Feature Ideas (based on intent above)

The following have been discussed or are natural next steps:

- **GEX chart** — compute Gamma Exposure per strike from OI × approximate gamma (needs vol surface or simplified ATM gamma assumption). Show as a bar chart with the flip level highlighted.
- **Intraday delta flow** — track how net delta is shifting throughout the day using periodic snapshots
- **0DTE key levels overlay** — on the Vol2Vol chart, mark the ±1σ/2σ levels and top OI strikes together as a "battlefield map"
- **OI concentration score** — single number showing how concentrated OI is around ATM vs spread out (kurtosis of the OI distribution)

---

## Vol2Vol Intraday Data Behavior (empirically verified)

These behaviors were confirmed by analyzing snapshot files for Gold contract G3WM6
across 25 intraday snapshots (notebooks/g3wm6_intraday_oi_monotonic.ipynb).

### 1. Intraday volume is cumulative within a CME session — not the full day

`call_value` / `put_value` in the Intraday tab accumulate monotonically within one
CME trading session. They are **NOT** cumulative across the entire calendar day.

CME resets the intraday counter at the daily maintenance window: **17:00–18:00 ET**
(≈ 04:00–05:00 Bangkok time). Any snapshot taken just after this window will show
values close to 0 even though earlier snapshots in the same calendar day had high
values. This means:

- A scraper running across the reset window will observe apparent "decreases" in
  intraday volume — this is expected and correct, not a bug or data error.
- When comparing snapshots from the same calendar day, check whether they are from
  the same session (both before or both after the reset time) before drawing
  conclusions about volume growth.

### 2. CME only returns strikes within ±3σ of the current futures price

QuikStrike does not return all strikes for a contract. It returns only the strikes
that fall within the ±3σ expected range **at the time of the fetch**. As expiration
approaches (DTE decreases), the 3σ range narrows — so later-in-the-day snapshots
have fewer strikes than earlier ones.

Practical consequences:
- A strike that was present in a 10:00 AM snapshot may be absent in a 3:00 PM
  snapshot simply because the futures price moved away from it and it fell outside
  the ±3σ window — not because trading stopped.
- The Intraday heatmap (see notebook) shows this clearly: active strike range
  contracts over time as IV / expected range narrows.
- Do not assume that a missing strike has zero volume; it may have had volume
  earlier that is now outside the fetch window.

---

## Important Constraints

- **No build step** — edits to `dashboard/index.html` are live immediately
- **Data refresh = page reload** — JS data files are loaded once at page load
- **Snapshots grow unbounded** — no cleanup implemented in `data/snapshots/`
- **Single HTML file** — all JS/CSS lives in `index.html` (~1200 lines)
- **Color scheme** — gold accent `#b45309`, red=puts, blue=calls
