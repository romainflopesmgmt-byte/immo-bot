"""Scrapers immobiliers."""

import logging

from scrapers.leboncoin import LeBonCoinScraper
from scrapers.pap_http import PAPHttpScraper

logger = logging.getLogger(__name__)

# Scrapers HTTP (toujours disponibles)
ALL_SCRAPERS = [LeBonCoinScraper, PAPHttpScraper]

# Charger les scrapers Playwright uniquement si disponible
try:
    from scrapers.bienici import BienIciScraper
    from scrapers.seloger import SeLogerScraper
    ALL_SCRAPERS.extend([BienIciScraper, SeLogerScraper])
except ImportError:
    logger.info("Playwright non disponible — scrapers Bien'ici/SeLoger désactivés")

__all__ = ["ALL_SCRAPERS"]
