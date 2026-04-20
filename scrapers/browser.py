"""Gestionnaire de navigateur Playwright partagé entre les scrapers."""

import logging
from contextlib import contextmanager

from playwright.sync_api import sync_playwright, Browser, Page

logger = logging.getLogger(__name__)


@contextmanager
def browser_context():
    """Context manager qui fournit un navigateur Playwright headless."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        timezone_id="Europe/Paris",
    )
    context.set_extra_http_headers({
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
    })
    try:
        yield context
    finally:
        context.close()
        browser.close()
        pw.stop()
