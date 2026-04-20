"""Scrapers immobiliers — LeBonCoin, Bien'ici, PAP, SeLoger."""

from scrapers.leboncoin import LeBonCoinScraper
from scrapers.bienici import BienIciScraper
from scrapers.pap import PAPScraper
from scrapers.seloger import SeLogerScraper

ALL_SCRAPERS = [LeBonCoinScraper, BienIciScraper, PAPScraper, SeLogerScraper]

__all__ = ["ALL_SCRAPERS", "LeBonCoinScraper", "BienIciScraper", "PAPScraper", "SeLogerScraper"]
