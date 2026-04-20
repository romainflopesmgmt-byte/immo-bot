"""Classe de base pour tous les scrapers immobiliers."""

import logging
import random
import time
from abc import ABC, abstractmethod

import httpx

from config import CITIES, FILTERS, SearchFilters, City
from database import Listing

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class BaseScraper(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers=self._base_headers(),
        )

    def _base_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _throttle(self, min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        time.sleep(random.uniform(min_sec, max_sec))

    def _matches_filters(self, listing: Listing) -> bool:
        if listing.price > FILTERS.price_max:
            return False
        if FILTERS.price_min and listing.price < FILTERS.price_min:
            return False
        if listing.surface < FILTERS.surface_min:
            return False
        if FILTERS.surface_max and listing.surface > FILTERS.surface_max:
            return False
        if FILTERS.rooms_min and listing.rooms and listing.rooms < FILTERS.rooms_min:
            return False
        if FILTERS.rooms_max and listing.rooms and listing.rooms > FILTERS.rooms_max:
            return False
        return True

    @abstractmethod
    def scrape(self) -> list[Listing]:
        """Scrape le site et retourne les annonces correspondant aux filtres."""

    def close(self) -> None:
        self.client.close()
