"""Scraper LeBonCoin — API interne + fallback Playwright."""

import json
import logging
import re

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper
from scrapers.browser import browser_context

logger = logging.getLogger(__name__)

LEBONCOIN_API = "https://api.leboncoin.fr/finder/search"
CATEGORY_MAP = {"buy": "9", "rent": "10"}
PROPERTY_TYPE_MAP = {"house": ["1"], "apartment": ["2"], "both": ["1", "2"]}

TARGET_ZIPCODES = {c.zipcode for c in CITIES}


class LeBonCoinScraper(BaseScraper):
    name = "leboncoin"

    def _build_payload(self) -> dict:
        locations = []
        for city in CITIES:
            locations.append({
                "city": city.name,
                "zipcode": city.zipcode,
                "department_id": city.department,
                "locationType": "city",
            })

        ranges: dict = {"price": {"max": FILTERS.price_max}}
        if FILTERS.price_min:
            ranges["price"]["min"] = FILTERS.price_min
        ranges["square"] = {"min": FILTERS.surface_min}
        if FILTERS.surface_max:
            ranges["square"]["max"] = FILTERS.surface_max
        if FILTERS.rooms_min:
            ranges["rooms"] = {"min": FILTERS.rooms_min}

        return {
            "limit": 50,
            "limit_alu": 3,
            "filters": {
                "category": {"id": CATEGORY_MAP.get(FILTERS.transaction, "9")},
                "enums": {
                    "real_estate_type": PROPERTY_TYPE_MAP.get(FILTERS.property_type, ["1"]),
                    "ad_type": ["offer"],
                },
                "location": {"locations": locations},
                "ranges": ranges,
            },
            "sort_by": "time",
            "sort_order": "desc",
        }

    def _parse_ad(self, ad: dict) -> Listing | None:
        try:
            price_list = ad.get("price", [])
            price = int(price_list[0]) if price_list else 0

            attributes = {a["key"]: a.get("value", "") for a in ad.get("attributes", [])}
            surface = int(attributes.get("square", "0").replace("m²", "").strip() or "0")
            rooms = int(attributes.get("rooms", "0") or "0") or None

            location = ad.get("location", {})
            city = location.get("city", "")
            zipcode = location.get("zipcode", "")

            images = ad.get("images", {})
            image_url = ""
            if images.get("urls"):
                image_url = images["urls"][0]

            return Listing(
                source="leboncoin",
                source_id=str(ad["list_id"]),
                title=ad.get("subject", "Sans titre"),
                price=price,
                surface=surface,
                rooms=rooms,
                city=city,
                zipcode=zipcode,
                url=f"https://www.leboncoin.fr/ad/ventes_immobilieres/{ad['list_id']}",
                image_url=image_url,
                description=ad.get("body", "")[:300],
            )
        except (KeyError, IndexError, ValueError) as exc:
            logger.debug("LeBonCoin parse erreur: %s", exc)
            return None

    def scrape(self) -> list[Listing]:
        logger.info("LeBonCoin — lancement du scan...")

        # Tentative 1 : API directe (rapide)
        results = self._scrape_api()
        if results:
            return results

        # Tentative 2 : Playwright (fiable si API rate-limitée)
        return self._scrape_playwright()

    def _scrape_api(self) -> list[Listing]:
        results: list[Listing] = []
        try:
            headers = {
                **self._base_headers(),
                "api_key": "ba0c2dad52b3ec",
                "Content-Type": "application/json",
                "Origin": "https://www.leboncoin.fr",
                "Referer": "https://www.leboncoin.fr/",
            }

            resp = self.client.post(
                LEBONCOIN_API,
                json=self._build_payload(),
                headers=headers,
            )

            if resp.status_code != 200:
                logger.warning("LeBonCoin API HTTP %s — passage au fallback", resp.status_code)
                return results

            data = resp.json()
            ads = data.get("ads", [])
            logger.info("LeBonCoin API — %d annonces trouvées", len(ads))

            for ad in ads:
                listing = self._parse_ad(ad)
                if listing and self._matches_filters(listing):
                    results.append(listing)

        except Exception as exc:
            logger.warning("LeBonCoin API erreur: %s", exc)

        self._throttle()
        return results

    def _scrape_playwright(self) -> list[Listing]:
        """Fallback Playwright quand l'API est bloquée."""
        logger.info("LeBonCoin — fallback Playwright...")
        results: list[Listing] = []

        # Construire l'URL de recherche avec les villes
        cities_param = "%2C".join(c.zipcode for c in CITIES)
        url = (
            "https://www.leboncoin.fr/recherche?category=9"
            "&real_estate_type=house"
            f"&price=0-{FILTERS.price_max}"
            f"&square={FILTERS.surface_min}-all"
            "&sort=time"
            "&owner_type=all"
        )

        try:
            with browser_context() as ctx:
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)

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

                # Extraire __NEXT_DATA__ si disponible
                next_data_el = page.query_selector("script#__NEXT_DATA__")
                if next_data_el:
                    json_text = next_data_el.inner_text()
                    next_data = json.loads(json_text)
                    ads = (
                        next_data.get("props", {})
                        .get("pageProps", {})
                        .get("searchData", {})
                        .get("ads", [])
                    )
                    logger.info("LeBonCoin Playwright __NEXT_DATA__ — %d annonces", len(ads))
                    for ad in ads:
                        listing = self._parse_ad(ad)
                        if listing and self._matches_filters(listing):
                            results.append(listing)
                else:
                    # Parse les cartes visuellement
                    results = self._parse_cards_playwright(page)

                page.close()

        except Exception as exc:
            logger.error("LeBonCoin Playwright erreur: %s", exc)

        logger.info("LeBonCoin Playwright — %d annonces filtrées", len(results))
        return results

    def _parse_cards_playwright(self, page) -> list[Listing]:
        """Parse les cartes d'annonces quand __NEXT_DATA__ n'est pas dispo."""
        results: list[Listing] = []

        links = page.query_selector_all("a[href*='/ad/ventes_immobilieres/']")
        logger.info("LeBonCoin Playwright — %d liens d'annonces", len(links))

        seen_ids: set[str] = set()
        for link in links:
            try:
                href = link.get_attribute("href") or ""
                ad_id_match = re.search(r"/ad/ventes_immobilieres/(\d+)", href)
                if not ad_id_match:
                    continue
                ad_id = ad_id_match.group(1)
                if ad_id in seen_ids:
                    continue
                seen_ids.add(ad_id)

                parent = link.evaluate_handle(
                    "el => el.closest('[data-testid]') || el.closest('article') || el.parentElement.parentElement"
                ).as_element()
                text = parent.inner_text() if parent else link.inner_text()

                # Prix
                price_match = re.search(r"([\d\s\.\xa0]+)\s*€", text)
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

                # Ville
                city, zipcode = "", ""
                for c in CITIES:
                    if c.name.lower() in text.lower() or c.zipcode in text:
                        city = c.name
                        zipcode = c.zipcode
                        break

                if price > 0 and city:
                    listing = Listing(
                        source="leboncoin",
                        source_id=ad_id,
                        title=f"Maison {surface}m² {city}" if surface else f"Maison {city}",
                        price=price,
                        surface=surface,
                        rooms=rooms,
                        city=city,
                        zipcode=zipcode,
                        url=f"https://www.leboncoin.fr{href}" if not href.startswith("http") else href,
                    )
                    if self._matches_filters(listing):
                        results.append(listing)

            except Exception:
                continue

        return results
