"""Scraper PAP (Particulier à Particulier) — via Playwright."""

import logging
import re

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper
from scrapers.browser import browser_context

logger = logging.getLogger(__name__)

PAP_BASE = "https://www.pap.fr"

# Zipcodes ciblés pour filtrer les résultats
TARGET_ZIPCODES = {c.zipcode for c in CITIES}
TARGET_CITY_NAMES = {c.name.lower() for c in CITIES}


class PAPScraper(BaseScraper):
    name = "pap"

    def _build_search_url(self) -> str:
        property_type = "maison" if FILTERS.property_type == "house" else "appartement"
        if FILTERS.property_type == "both":
            property_type = "maison-appartement"

        return (
            f"{PAP_BASE}/annonce/vente-{property_type}-val-de-marne-94"
            f"?prix-max={FILTERS.price_max}"
            f"&surface-min={FILTERS.surface_min}"
        )

    def _parse_link(self, link_el) -> Listing | None:
        try:
            href = link_el.get_attribute("href") or ""
            if not href or "/annonces/" not in href:
                return None

            full_url = f"{PAP_BASE}{href}" if not href.startswith("http") else href

            # ID: /annonces/maison-saint-maur-94100-r460601755 → r460601755
            ad_id_match = re.search(r"-r(\d+)$", href.rstrip("/"))
            ad_id = ad_id_match.group(1) if ad_id_match else ""
            if not ad_id:
                return None

            # Texte du lien contient : prix, ville, pièces, surface
            text = link_el.inner_text()
            if not text.strip():
                return None

            # Prix : "470.000 €" ou "350 000 €"
            price_match = re.search(r"([\d\.\s]+)\s*€", text)
            price = 0
            if price_match:
                price_str = price_match.group(1).replace(".", "").replace(" ", "")
                price = int(price_str) if price_str.isdigit() else 0

            # Surface : "120 m²"
            surface_match = re.search(r"(\d+)\s*m[²2]", text)
            surface = int(surface_match.group(1)) if surface_match else 0

            # Pièces : "5 pièces"
            rooms_match = re.search(r"(\d+)\s*pi[eè]ce", text)
            rooms = int(rooms_match.group(1)) if rooms_match else None

            # Ville et code postal : "Saint-Maur-des-Fossés (94100)"
            loc_match = re.search(r"([A-ZÀ-Ÿa-zà-ÿ\-\s]+)\s*\((\d{5})\)", text)
            city = loc_match.group(1).strip() if loc_match else ""
            zipcode = loc_match.group(2) if loc_match else ""

            # Vérifier que c'est dans nos villes cibles
            in_target = False
            if zipcode in TARGET_ZIPCODES:
                in_target = True
            elif city:
                for target_name in TARGET_CITY_NAMES:
                    if target_name in city.lower() or city.lower() in target_name:
                        in_target = True
                        break

            if not in_target:
                return None

            # Titre
            title_parts = [p.strip() for p in text.split("\n") if p.strip()]
            title = title_parts[0] if title_parts else f"Maison {surface}m² {city}"

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
                url=full_url,
            )
        except Exception as exc:
            logger.debug("PAP parse erreur: %s", exc)
            return None

    def scrape(self) -> list[Listing]:
        logger.info("PAP — lancement du scan Playwright...")
        results: list[Listing] = []

        try:
            with browser_context() as ctx:
                page = ctx.new_page()
                url = self._build_search_url()

                page.goto(url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(2000)

                # Accepter les cookies si popup
                try:
                    cookie_btn = page.query_selector(
                        "#didomi-notice-agree-button, "
                        "button[id*='accept'], "
                        "[id*='consent'] button"
                    )
                    if cookie_btn and cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

                # Sélectionner tous les liens d'annonces
                links = page.query_selector_all("a[href*='/annonces/']")
                logger.info("PAP — %d liens d'annonces trouvés", len(links))

                seen_ids: set[str] = set()
                for link in links:
                    listing = self._parse_link(link)
                    if listing and listing.source_id not in seen_ids and self._matches_filters(listing):
                        seen_ids.add(listing.source_id)
                        results.append(listing)

                page.close()

        except Exception as exc:
            logger.error("PAP Playwright erreur: %s", exc)

        logger.info("PAP — %d annonces filtrées", len(results))
        return results
