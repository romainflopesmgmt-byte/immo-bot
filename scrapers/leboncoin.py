"""Scraper LeBonCoin — ScraperAPI (gratuit) pour bypass DataDome."""

import json
import logging
import os
import random
import re
import subprocess
import time
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from config import CITIES, FILTERS
from database import Listing
from scrapers.base import BaseScraper, USER_AGENTS

logger = logging.getLogger(__name__)

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
LEBONCOIN_API = "https://api.leboncoin.fr/finder/search"
CATEGORY_MAP = {"buy": "9", "rent": "10"}
PROPERTY_TYPE_MAP = {"house": ["1"], "apartment": ["2"], "both": ["1", "2"]}


class LeBonCoinScraper(BaseScraper):
    name = "leboncoin"

    def _build_search_url(self) -> str:
        """Construit l'URL de recherche LeBonCoin."""
        params = {
            "category": CATEGORY_MAP.get(FILTERS.transaction, "9"),
            "real_estate_type": "house" if FILTERS.property_type == "house" else "flat",
            "locations": "d_94",
            "price": f"min-{FILTERS.price_min}-max-{FILTERS.price_max}" if FILTERS.price_min else f"max-{FILTERS.price_max}",
            "square": f"min-{FILTERS.surface_min}",
            "sort": "time",
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://www.leboncoin.fr/recherche?{qs}"

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

    def _parse_html_listing(self, card, idx: int) -> Listing | None:
        """Parse une carte d'annonce depuis le HTML rendu."""
        try:
            text = card.get_text(" ", strip=True)

            # Prix
            price_match = re.search(r"([\d\s\.]+)\s*€", text)
            price = 0
            if price_match:
                price_str = re.sub(r"[^\d]", "", price_match.group(1))
                price = int(price_str) if price_str else 0

            # Surface
            surf_match = re.search(r"(\d+)\s*m[²2]", text)
            surface = int(surf_match.group(1)) if surf_match else 0

            # Pièces
            rooms_match = re.search(r"(\d+)\s*(?:pi[èe]ce|p\.)", text)
            rooms = int(rooms_match.group(1)) if rooms_match else None

            # Lien
            link = card.select_one("a[href*='/ad/']") or card.select_one("a[href*='/ventes']")
            href = link.get("href", "") if link else ""
            ad_id_match = re.search(r"/(\d+)(?:\?|$)", href)
            ad_id = ad_id_match.group(1) if ad_id_match else str(idx)

            full_url = f"https://www.leboncoin.fr{href}" if href and not href.startswith("http") else href

            # Ville
            city = ""
            zipcode = ""
            for c in CITIES:
                if c.name.lower() in text.lower() or c.zipcode in text:
                    city = c.name
                    zipcode = c.zipcode
                    break

            if price == 0:
                return None

            return Listing(
                source="leboncoin",
                source_id=ad_id,
                title=text[:80],
                price=price,
                surface=surface,
                rooms=rooms,
                city=city,
                zipcode=zipcode,
                url=full_url or f"https://www.leboncoin.fr/ad/ventes_immobilieres/{ad_id}",
            )
        except Exception as exc:
            logger.debug("LeBonCoin HTML parse erreur: %s", exc)
            return None

    def scrape(self) -> list[Listing]:
        logger.info("LeBonCoin — lancement du scan...")

        # Methode 1 : ScraperAPI (rendu navigateur = bypass DataDome)
        if SCRAPER_API_KEY:
            results = self._scrape_via_scraperapi()
            if results:
                return results

        # Methode 2 : curl direct API (peut etre bloque)
        results = self._scrape_curl_api()
        if results:
            return results

        if not SCRAPER_API_KEY:
            logger.warning(
                "LeBonCoin — bloqué par DataDome. "
                "Ajoute SCRAPER_API_KEY (gratuit sur scraperapi.com) pour contourner."
            )
        return []

    def _scrape_via_scraperapi(self) -> list[Listing]:
        """Utilise ScraperAPI pour rendre la page de recherche LeBonCoin."""
        results: list[Listing] = []
        try:
            search_url = self._build_search_url()
            api_url = (
                f"http://api.scraperapi.com"
                f"?api_key={SCRAPER_API_KEY}"
                f"&url={urllib.parse.quote(search_url)}"
                f"&render=true"
                f"&country_code=fr"
            )

            logger.info("LeBonCoin ScraperAPI — fetch page de recherche...")
            resp = httpx.get(api_url, timeout=60)

            if resp.status_code != 200:
                logger.warning("LeBonCoin ScraperAPI HTTP %s", resp.status_code)
                return results

            soup = BeautifulSoup(resp.text, "html.parser")

            # LeBonCoin utilise des balises <a> avec data-test-id ou class contenant "ad"
            cards = (
                soup.select("[data-test-id*='ad']")
                or soup.select("a[href*='/ad/']")
                or soup.select("[class*='adCard']")
                or soup.select("[class*='listing']")
            )

            logger.info("LeBonCoin ScraperAPI — %d cartes trouvées", len(cards))

            for idx, card in enumerate(cards):
                listing = self._parse_html_listing(card, idx)
                if listing and self._matches_filters(listing):
                    results.append(listing)

            logger.info("LeBonCoin ScraperAPI — %d annonces après filtres", len(results))

        except Exception as exc:
            logger.warning("LeBonCoin ScraperAPI erreur: %s", exc)

        self._throttle()
        return results

    def _scrape_curl_api(self) -> list[Listing]:
        """Appel API direct via curl (fonctionne si pas de captcha)."""
        results: list[Listing] = []
        try:
            payload = json.dumps(self._build_payload())
            result = subprocess.run(
                [
                    "curl", "-sL", "-X", "POST",
                    LEBONCOIN_API,
                    "-H", f"User-Agent: {random.choice(USER_AGENTS)}",
                    "-H", "Content-Type: application/json",
                    "-H", "api_key: ba0c2dad52b3ec",
                    "-H", "Origin: https://www.leboncoin.fr",
                    "-H", "Referer: https://www.leboncoin.fr/",
                    "-H", "Accept: application/json",
                    "-d", payload,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            body = result.stdout.strip()
            if not body:
                logger.warning("LeBonCoin curl — réponse vide")
                return results

            data = json.loads(body)

            # Detecter captcha DataDome
            if "captcha-delivery" in data.get("url", ""):
                logger.warning("LeBonCoin curl — CAPTCHA DataDome détecté")
                return results

            ads = data.get("ads", [])
            logger.info("LeBonCoin curl — %d annonces", len(ads))

            for ad in ads:
                listing = self._parse_ad(ad)
                if listing and self._matches_filters(listing):
                    results.append(listing)

        except json.JSONDecodeError:
            logger.warning("LeBonCoin curl — réponse non-JSON (probablement captcha)")
        except Exception as exc:
            logger.warning("LeBonCoin curl erreur: %s", exc)

        self._throttle()
        return results
