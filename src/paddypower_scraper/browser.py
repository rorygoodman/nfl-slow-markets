"""Playwright-driven browser session for Cloudflare-gated PaddyPower calls.

One BrowserSession per scraper run. Warms up once on __enter__ to earn
the cf_clearance cookie, then reuses the same browser context for every
fetch_json call."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Type

from playwright.sync_api import Playwright, sync_playwright

from .api import LOCALE, TIMEZONE, USER_AGENT, WARMUP_URL


class BrowserFetchError(Exception):
    """Raised when an in-page fetch returns non-2xx, fails to evaluate,
    or returns invalid JSON."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


_FETCH_JS = """
async ([url, timeoutMs]) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const r = await fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: { 'accept': 'application/json, text/plain, */*' },
            signal: controller.signal,
        });
        if (!r.ok) {
            const text = await r.text();
            throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 500));
        }
        return await r.text();
    } finally {
        clearTimeout(timer);
    }
}
"""


class BrowserSession:
    """Context manager. Launches headless Chromium and warms it up on
    __enter__; closes everything on __exit__."""

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            locale=LOCALE,
            timezone_id=TIMEZONE,
        )
        self._page = self._context.new_page()
        self._page.goto(WARMUP_URL, timeout=20_000)
        self._page.wait_for_load_state("domcontentloaded", timeout=15_000)
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw is not None:
                self._pw.stop()

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        """Run an in-page fetch() against `url` and return the parsed JSON.

        Raises BrowserFetchError on HTTP non-2xx, evaluation failure, or
        invalid JSON."""
        if self._page is None:
            raise RuntimeError("BrowserSession not entered")
        try:
            body = self._page.evaluate(_FETCH_JS, [url, timeout_ms])
        except Exception as e:
            raise BrowserFetchError(url, str(e)) from e
        if not isinstance(body, str):
            raise BrowserFetchError(url, f"unexpected response type: {type(body).__name__}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise BrowserFetchError(url, f"invalid JSON: {e}") from e
