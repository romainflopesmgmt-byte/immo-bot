"""Scrapers immobiliers."""

import logging

from scrapers.leboncoin import LeBonCoinScraper

logger = logging.getLogger(__name__)

ALL_SCRAPERS = [LeBonCoinScraper]

# Charger les scrapers Playwright uniquement si disponible
try:
    from scrapers.bienici import BienIciScraper
    from scrapers.pap import PAPScraper
    from scrapers.seloger import SeLogerScraper
    ALL_SCRAPERS.extend([BienIciScraper, PAPScraper, SeLogerScraper])
except ImportError:
    logger.info("Playwright non disponible — scrapers Bien'ici/PAP/SeLoger désactivés")

__all__ = ["ALL_SCRAPERS"]
