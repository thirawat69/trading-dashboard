"""
Session management for QuikStrike.

setup()        — login + capture insid/qsid → save session.json
Session.load() — load saved tokens from data/session.json
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

SESSION_FILE = Path(__file__).parent.parent / "data" / "session.json"
SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

ENV_FILE    = Path(__file__).parent.parent / ".env"
LOGIN_URL   = "https://login.cmegroup.com/sso/accountstatus/showAuth.action"
VOL2VOL_URL = (
    "https://www.cmegroup.com/tools-information/quikstrike/"
    "vol2vol-expected-range.html"
)


class SessionExpiredError(Exception):
    """Raised when QuikStrike redirects to ErrorPage.aspx (session expired/denied)."""


@dataclass
class Session:
    insid: str = ""
    qsid: str  = ""

    @classmethod
    def load(cls) -> "Session":
        if not SESSION_FILE.exists():
            raise FileNotFoundError("Run: python scrapers/session.py")
        data = json.loads(SESSION_FILE.read_text())
        return cls(insid=data.get("insid", ""), qsid=data.get("qsid", ""))

    def save(self):
        existing = json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else {}
        existing["insid"] = self.insid
        existing["qsid"]  = self.qsid
        SESSION_FILE.write_text(json.dumps(existing, indent=2))
        print(f"  Tokens saved (insid={self.insid}, qsid={self.qsid[:8]}...)")

    @property
    def is_valid(self) -> bool:
        return bool(self.insid and self.qsid)


def _load_credentials() -> tuple:
    load_dotenv(ENV_FILE)
    email    = os.getenv("CME_EMAIL", "")
    password = os.getenv("CME_PASSWORD", "")
    if not email or not password:
        raise ValueError(f"CME_EMAIL or CME_PASSWORD missing in {ENV_FILE}")
    return email, password


def _extract_tokens(url: str) -> tuple:
    params = parse_qs(urlparse(url).query)
    return params.get("insid", [""])[0], params.get("qsid", [""])[0]


def setup(headless: bool = False):
    """Login to CME Group, navigate to Vol2Vol, capture insid/qsid, save session."""

    # 1. อ่าน credentials
    email, password = _load_credentials()
    print(f"  Credentials loaded ({email})")

    captured: dict = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=200)
        context = browser.new_context()
        page    = context.new_page()

        # listener จับ insid/qsid จาก QuikStrike requests
        def on_request(request):
            if "quikstrike" in request.url.lower() or "QuikStrike" in request.url:
                print(f"  [req] {request.url[:120]}")
            if "QuikStrikeView.aspx" in request.url and "insid=" in request.url:
                insid, qsid = _extract_tokens(request.url)
                if insid and qsid and not captured.get("insid"):
                    captured["insid"] = insid
                    captured["qsid"]  = qsid
                    print(f"  Captured insid={insid}, qsid={qsid[:8]}...")

        page.on("request", on_request)

        # 2. Login
        print("  Logging in...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        page.fill("#user", email)
        page.fill("#pwd", password)
        page.click("#loginBtn")
        page.wait_for_url("*www.cmegroup.com*", timeout=30000, wait_until="commit")
        print("  Login OK")

        # 3. ไปหน้า Vol2Vol รอ QuikStrike iframe โหลด
        print("  Loading Vol2Vol...")
        page.goto(VOL2VOL_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(10000)

        if not captured.get("insid"):
            print("  Tokens not yet captured — waiting 10s more...")
            page.wait_for_timeout(10000)

        # 4. บันทึก
        context.storage_state(path=str(SESSION_FILE))
        print(f"  Cookies saved -> {SESSION_FILE}")

        if captured.get("insid"):
            Session(insid=captured["insid"], qsid=captured["qsid"]).save()
            print(f"  Session ready -> {SESSION_FILE}")
        else:
            print("  WARNING: insid/qsid not captured — run session.py again")

        browser.close()


if __name__ == "__main__":
    setup()
