"""Scraper PAP — HTTP pur avec BeautifulSoup (pas besoin de Playwright)."""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

TARGET_ZIPCODES = {c.zipcode for c in CITIES}
PAP_BASE = "https://www.pap.fr"


class PAPHttpScraper(BaseScraper):
    name = "pap"

    def _build_url(self, page: int = 1) -> str:
        prop = "maisons" if FILTERS.property_type == "house" else "appartements"
        if FILTERS.property_type == "both":
            prop = "maisons-appartements"

        url = f"{PAP_BASE}/annonce/vente-{prop}"
        params = []
        if FILTERS.price_max:
            params.append(f"prix-max={FILTERS.price_max}")
        if FILTERS.surface_min:
            params.append(f"surface-min={FILTERS.surface_min}")
        if page > 1:
            params.append(f"page={page}")
        if params:
            url += "?" + "&".join(params)
        return url

    def _parse_item(self, item) -> Listing | None:
        try:
            # Lien et ID
            link = item.select_one("a[href*='/annonces/']")
            if not link:
                return None
            href = link.get("href", "")

            # Extraire zipcode du href : /annonces/maison-saint-maur-94100-r449900226
            zc_match = re.search(r"-(\d{5})-r(\d+)", href)
            if not zc_match:
                return None

            zipcode = zc_match.group(1)
            ad_id = zc_match.group(2)

            # Filtrer par zipcode cible
            if zipcode not in TARGET_ZIPCODES:
                return None

            # Prix
            price_el = item.select_one(".item-price")
            price = 0
            if price_el:
                price_text = price_el.get_text(strip=True)
                price_clean = re.sub(r"[^\d]", "", price_text)
                price = int(price_clean) if price_clean else 0

            # Tags : pièces, chambres, surface
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
            # href like /annonces/maison-saint-maur-des-fosses-94100-rXXX
            city_match = re.search(r"/annonces/\w+-(.+)-\d{5}-r\d+", href)
            if city_match:
                city_slug = city_match.group(1)
                city = city_slug.replace("-", " ").title()

            # Description
            desc_el = item.select_one(".item-description")
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            # Titre
            title_parts = []
            if surface:
                title_parts.append(f"Maison {surface}m²")
            else:
                title_parts.append("Maison")
            if city:
                title_parts.append(city)
            title = " — ".join(title_parts)

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
            logger.debug("PAP HTTP parse erreur: %s", exc)
            return None

    def scrape(self) -> list[Listing]:
        logger.info("PAP HTTP — lancement du scan...")
        results: list[Listing] = []
        seen_ids: set[str] = set()

        # Scanner les 5 premières pages
        for page_num in range(1, 6):
            try:
                url = self._build_url(page_num)
                resp = self.client.get(url)

                if resp.status_code != 200:
                    logger.warning("PAP HTTP page %d — HTTP %s", page_num, resp.status_code)
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".search-list-item-alt")

                if not items:
                    logger.info("PAP HTTP — page %d vide, arrêt pagination", page_num)
                    break

                page_count = 0
                for item in items:
                    listing = self._parse_item(item)
                    if listing and listing.source_id not in seen_ids and self._matches_filters(listing):
                        seen_ids.add(listing.source_id)
                        results.append(listing)
                        page_count += 1

                logger.info("PAP HTTP — page %d: %d items, %d matchent 94",
                            page_num, len(items), page_count)

                self._throttle(1.0, 2.0)

            except Exception as exc:
                logger.warning("PAP HTTP page %d erreur: %s", page_num, exc)
                break

        logger.info("PAP HTTP — %d annonces au total", len(results))
        return results
