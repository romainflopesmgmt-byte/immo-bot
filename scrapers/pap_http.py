"""Scraper PAP — subprocess curl + BeautifulSoup (aucune dep anti-bot)."""

import logging
import re
import subprocess

from bs4 import BeautifulSoup

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

TARGET_ZIPCODES = {c.zipcode for c in CITIES}
PAP_BASE = "https://www.pap.fr"


def _curl_get(url: str) -> str:
    """Fetch une URL avec curl (TLS fingerprint normal)."""
    result = subprocess.run(
        [
            "curl", "-sL", url,
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "-H", "Accept-Language: fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


class PAPHttpScraper(BaseScraper):
    name = "pap"

    def _parse_item(self, item) -> Listing | None:
        try:
            link = item.select_one("a[href*='/annonces/']")
            if not link:
                return None
            href = link.get("href", "")

            zc_match = re.search(r"-(\d{5})-r(\d+)", href)
            if not zc_match:
                return None

            zipcode = zc_match.group(1)
            ad_id = zc_match.group(2)

            if zipcode not in TARGET_ZIPCODES:
                return None

            # Prix
            price_el = item.select_one(".item-price")
            price = 0
            if price_el:
                price_clean = re.sub(r"[^\d]", "", price_el.get_text(strip=True))
                price = int(price_clean) if price_clean else 0

            # Tags
            rooms = None
            surface = 0
            for tag in item.select(".item-tags li"):
                tag_text = tag.get_text(strip=True)
                room_match = re.search(r"(\d+)\s*pi", tag_text)
                if room_match:
                    rooms = int(room_match.group(1))
                surf_match = re.search(r"(\d+)\s*m", tag_text)
                if surf_match and "chambre" not in tag_text and "pi" not in tag_text:
                    surface = int(surf_match.group(1))

            # Ville depuis le href
            city = ""
            city_match = re.search(r"/annonces/\w+-(.+)-\d{5}-r\d+", href)
            if city_match:
                city = city_match.group(1).replace("-", " ").title()

            desc_el = item.select_one(".item-description")
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            title = f"Maison {surface}m²" if surface else "Maison"
            if city:
                title += f" {city}"

            if price == 0:
                return None

            return Listing(
                source="pap",
                source_id=ad_id,
                title=title,
                price=price,
                surface=surface,
                rooms=rooms,
                city=city,
                zipcode=zipcode,
                url=f"{PAP_BASE}{href}",
                description=description,
            )
        except Exception as exc:
            logger.debug("PAP parse erreur: %s", exc)
            return None

    def scrape(self) -> list[Listing]:
        logger.info("PAP — lancement du scan HTTP (curl)...")
        results: list[Listing] = []
        seen_ids: set[str] = set()

        for page_num in range(1, 11):
            try:
                url = f"{PAP_BASE}/annonce/vente-maisons?page={page_num}"
                html = _curl_get(url)
                if not html:
                    logger.warning("PAP page %d — réponse vide", page_num)
                    break

                soup = BeautifulSoup(html, "html.parser")
                items = soup.select(".search-list-item-alt")
                if not items:
                    break

                page_matches = 0
                for item in items:
                    listing = self._parse_item(item)
                    if listing and listing.source_id not in seen_ids and self._matches_filters(listing):
                        seen_ids.add(listing.source_id)
                        results.append(listing)
                        page_matches += 1

                logger.info("PAP page %d — %d items, %d matchent", page_num, len(items), page_matches)
                self._throttle(1.0, 2.0)

            except Exception as exc:
                logger.warning("PAP page %d erreur: %s", page_num, exc)
                break

        logger.info("PAP — %d annonces au total", len(results))
        return results
