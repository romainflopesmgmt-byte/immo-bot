"""Scraper Bien'ici — via Playwright (navigateur headless)."""

import logging
import re

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper
from scrapers.browser import browser_context

logger = logging.getLogger(__name__)

TARGET_ZIPCODES = {c.zipcode for c in CITIES}
TARGET_CITY_NAMES = {c.name.lower() for c in CITIES}


class BienIciScraper(BaseScraper):
    name = "bienici"

    def _parse_card_text(self, text: str, href: str) -> Listing | None:
        """Parse le texte d'une carte d'annonce Bien'ici."""
        if not text.strip():
            return None

        # Prix
        price_match = re.search(r"([\d\s\.]+)\s*€", text)
        price = 0
        if price_match:
            price_str = price_match.group(1).replace(".", "").replace(" ", "").replace("\xa0", "")
            price = int(price_str) if price_str.isdigit() else 0

        # Surface
        surface_match = re.search(r"(\d+)\s*m[²2]", text)
        surface = int(surface_match.group(1)) if surface_match else 0

        # Pièces
        rooms_match = re.search(r"(\d+)\s*pi[eè]ce", text)
        rooms = int(rooms_match.group(1)) if rooms_match else None

        # Ville / code postal
        city, zipcode = "", ""
        for c in CITIES:
            if c.zipcode in text or c.name.lower() in text.lower():
                city = c.name
                zipcode = c.zipcode
                break

        # Vérifier dans le href aussi
        if not city:
            for c in CITIES:
                slug = c.name.lower().replace(" ", "-").replace("é", "e").replace("è", "e")
                if slug in href.lower() or c.zipcode in href:
                    city = c.name
                    zipcode = c.zipcode
                    break

        if not city:
            return None

        # ID depuis le href
        ad_id = href.rstrip("/").split("/")[-1] if href else ""
        full_url = f"https://www.bienici.com{href}" if href and not href.startswith("http") else href

        if price == 0 or not ad_id:
            return None

        return Listing(
            source="bienici",
            source_id=str(ad_id),
            title=f"Maison {surface}m² {city}" if surface else f"Maison {city}",
            price=price,
            surface=surface,
            rooms=rooms,
            city=city,
            zipcode=zipcode,
            url=full_url or f"https://www.bienici.com/annonce/{ad_id}",
        )

    def scrape(self) -> list[Listing]:
        logger.info("Bien'ici — lancement du scan...")
        results: list[Listing] = []
        seen_ids: set[str] = set()

        try:
            with browser_context() as ctx:
                page = ctx.new_page()

                # Une seule recherche pour tout le Val-de-Marne
                url = (
                    "https://www.bienici.com/recherche/achat/val-de-marne-94"
                    f"/maisonvilla?prix-max={FILTERS.price_max}"
                    f"&surface-min={FILTERS.surface_min}"
                    "&tri=publication-desc"
                )

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # Attendre que le contenu se charge
                    page.wait_for_timeout(5000)

                    # Accepter cookies
                    try:
                        cookie_btn = page.query_selector(
                            "#didomi-notice-agree-button, "
                            "button[id*='accept']"
                        )
                        if cookie_btn and cookie_btn.is_visible():
                            cookie_btn.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # Chercher les liens d'annonces
                    ad_links = page.query_selector_all("a[href*='/annonce/']")
                    logger.info("Bien'ici — %d liens d'annonces trouvés", len(ad_links))

                    for link in ad_links:
                        try:
                            href = link.get_attribute("href") or ""
                            # Remonter au conteneur parent pour avoir le texte complet
                            parent = link.evaluate_handle(
                                "el => el.closest('[class*=\"card\"]') || el.closest('[class*=\"Card\"]') || el.closest('article') || el.parentElement.parentElement"
                            ).as_element()
                            text = parent.inner_text() if parent else link.inner_text()

                            listing = self._parse_card_text(text, href)
                            if listing and listing.source_id not in seen_ids and self._matches_filters(listing):
                                seen_ids.add(listing.source_id)
                                results.append(listing)
                        except Exception:
                            continue

                except Exception as exc:
                    logger.warning("Bien'ici erreur: %s", exc)

                page.close()

        except Exception as exc:
            logger.error("Bien'ici Playwright erreur: %s", exc)

        logger.info("Bien'ici — %d annonces au total", len(results))
        return results
