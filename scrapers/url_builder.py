"""QuikStrike URL builder"""

BASE_URL = "https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"

PRODUCTS: dict[str, dict] = {
    "gold":    {"pid": 40,  "pf": 6},
    "silver":  {"pid": 41,  "pf": 6},
    "nasdaq":  {"pid": 121, "pf": 26},
    "sp500":   {"pid": 103, "pf": 26},
}

TOOLS: dict[str, str] = {
    "vol2vol":    "IntegratedV2VExpectedRange",
    "oi_heatmap": "IntegratedVOIHeatMap",
    "cot":        "IntegratedCOT",
}


def build_url(product: str, tool: str, insid: str, qsid: str) -> str:
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product '{product}'. Options: {list(PRODUCTS)}")
    if tool not in TOOLS:
        raise ValueError(f"Unknown tool '{tool}'. Options: {list(TOOLS)}")

    p = PRODUCTS[product]
    return (
        f"{BASE_URL}"
        f"?pid={p['pid']}&pf={p['pf']}"
        f"&viewitemid={TOOLS[tool]}"
        f"&insid={insid}&qsid={qsid}"
    )
