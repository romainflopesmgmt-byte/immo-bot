"""Scraper LeBonCoin — API interne avec session cookies."""

import json
import logging
import random
import re
import time

import httpx

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper, USER_AGENTS

logger = logging.getLogger(__name__)

LEBONCOIN_API = "https://api.leboncoin.fr/finder/search"
CATEGORY_MAP = {"buy": "9", "rent": "10"}
PROPERTY_TYPE_MAP = {"house": ["1"], "apartment": ["2"], "both": ["1", "2"]}


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

        # Tentative 1 : API avec session cookies
        results = self._scrape_with_session()
        if results:
            return results

        # Tentative 2 : API directe (fallback)
        results = self._scrape_api_direct()
        if results:
            return results

        logger.warning("LeBonCoin — aucune méthode n'a fonctionné")
        return []

    def _scrape_with_session(self) -> list[Listing]:
        """Etablit une session en visitant LeBonCoin d'abord, puis appelle l'API."""
        results: list[Listing] = []
        ua = random.choice(USER_AGENTS)

        try:
            # Créer un client avec cookies persistants
            session = httpx.Client(
                timeout=30,
                follow_redirects=True,
                http2=False,
            )

            # Etape 1 : visiter la page d'accueil pour obtenir les cookies
            home_headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }

            logger.info("LeBonCoin — établissement de la session...")
            home_resp = session.get("https://www.leboncoin.fr/", headers=home_headers)
            logger.info("LeBonCoin — page d'accueil HTTP %s, cookies: %d",
                        home_resp.status_code, len(session.cookies))

            time.sleep(random.uniform(1.5, 3.0))

            # Etape 2 : appeler l'API avec les cookies de session
            api_headers = {
                "User-Agent": ua,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json",
                "api_key": "ba0c2dad52b3ec",
                "Origin": "https://www.leboncoin.fr",
                "Referer": "https://www.leboncoin.fr/recherche?category=9&real_estate_type=house",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "Connection": "keep-alive",
            }

            resp = session.post(
                LEBONCOIN_API,
                json=self._build_payload(),
                headers=api_headers,
            )

            session.close()

            if resp.status_code != 200:
                logger.warning("LeBonCoin session API HTTP %s", resp.status_code)
                return results

            data = resp.json()
            ads = data.get("ads", [])
            logger.info("LeBonCoin session — %d annonces trouvées", len(ads))

            for ad in ads:
                listing = self._parse_ad(ad)
                if listing and self._matches_filters(listing):
                    results.append(listing)

        except Exception as exc:
            logger.warning("LeBonCoin session erreur: %s", exc)

        self._throttle()
        return results

    def _scrape_api_direct(self) -> list[Listing]:
        """Appel API direct sans session (méthode originale)."""
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
                logger.warning("LeBonCoin API directe HTTP %s", resp.status_code)
                return results

            data = resp.json()
            ads = data.get("ads", [])
            logger.info("LeBonCoin API directe — %d annonces", len(ads))

            for ad in ads:
                listing = self._parse_ad(ad)
                if listing and self._matches_filters(listing):
                    results.append(listing)

        except Exception as exc:
            logger.warning("LeBonCoin API directe erreur: %s", exc)

        self._throttle()
        return results
