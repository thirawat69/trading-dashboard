"""Playwright helpers shared across all fetchers."""

import asyncio
from typing import Callable, Optional

from session import SessionExpiredError


async def safe_goto(page, url: str, **kwargs):
    """page.goto() that raises SessionExpiredError if QuikStrike redirects to error page."""
    await page.goto(url, **kwargs)
    if "ErrorPage.aspx" in page.url:
        raise SessionExpiredError(
            f"QuikStrike session expired — run: python scrapers/session.py\n"
            f"  URL: {page.url}"
        )


async def wait_for_updatepanel_idle(page, timeout: float = 20.0):
    """Wait for ASP.NET UpdatePanel to finish any in-flight async postback."""
    try:
        await page.wait_for_function(
            """() => {
                try {
                    return !Sys.WebForms.PageRequestManager
                        .getInstance().get_isInAsyncPostBack();
                } catch(e) { return true; }
            }""",
            timeout=int(timeout * 1000),
        )
    except Exception:
        pass  # timeout or Sys not defined → assume idle


async def expect_body(
    page,
    predicate: Callable,
    action,
    body_check: Optional[Callable[[str], bool]] = None,
    timeout: float = 10.0,
) -> Optional[str]:
    """
    Execute `action` (a coroutine) and return the body of the first response
    that matches `predicate` AND passes `body_check` (if given).

    Body is read immediately inside the response handler so Chrome doesn't GC
    it before we call .text() — fixes 'No data found for resource' CDP errors.

    If body_check is provided, intermediate responses that don't pass it are
    ignored and the listener keeps waiting (handles multi-response UpdatePanel).

    Returns None on timeout or read error.
    """
    future: asyncio.Future = asyncio.Future()

    async def on_response(response):
        if predicate(response) and not future.done():
            try:
                body = await response.text()
                if body_check is None or body_check(body):
                    future.set_result(body)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)

    page.on("response", on_response)
    try:
        await action
        # shield() keeps the future alive even if wait_for cancels on timeout
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None
    finally:
        page.remove_listener("response", on_response)
