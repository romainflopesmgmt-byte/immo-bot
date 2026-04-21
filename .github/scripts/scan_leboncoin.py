"""
LeBonCoin scanner via Playwright — tourne dans GitHub Actions.
Intercepte la réponse API dans le navigateur pour bypass DataDome.
"""

import json
import os
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

# --- Config ---
CITIES = {
    "94100": "Saint-Maur-des-Fossés",
    "94210": "Saint-Maur-des-Fossés",
    "94430": "Chennevières-sur-Marne",
    "94340": "Joinville-le-Pont",
    "94360": "Bry-sur-Marne",
    "94170": "Le Perreux-sur-Marne",
    "94130": "Nogent-sur-Marne",
    "94420": "Le Plessis-Trévise",
    "94490": "Ormesson-sur-Marne",
    "94500": "Champigny-sur-Marne",
}
TARGET_ZIPCODES = set(CITIES.keys())
PRICE_MAX = 420_000
SURFACE_MIN = 100

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SEEN_FILE = os.getenv("SEEN_FILE", "seen_ids.json")

SEARCH_URL = (
    "https://www.leboncoin.fr/recherche"
    "?category=9"
    "&real_estate_type=house"
    "&locations=d_94"
    f"&price=max-{PRICE_MAX}"
    f"&square=min-{SURFACE_MIN}"
    "&sort=time"
)


def load_seen_ids() -> set:
    if os.path.exists(SEEN_FILE):
        return set(json.load(open(SEEN_FILE)))
    return set()


def save_seen_ids(ids: set):
    json.dump(sorted(ids), open(SEEN_FILE, "w"))


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM SKIP] {message[:100]}")
        return
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        print(f"[TELEGRAM] {resp.status_code}")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


def format_listing(ad: dict) -> str:
    """Formate une annonce pour Telegram."""
    title = ad.get("subject", "Sans titre")
    price_list = ad.get("price", [])
    price = int(price_list[0]) if price_list else 0

    attrs = {a["key"]: a.get("value", "") for a in ad.get("attributes", [])}
    surface = attrs.get("square", "?").replace("m²", "").strip()
    rooms = attrs.get("rooms", "?")

    location = ad.get("location", {})
    city = location.get("city", "")
    zipcode = location.get("zipcode", "")

    ad_id = ad.get("list_id", "")
    url = f"https://www.leboncoin.fr/ad/ventes_immobilieres/{ad_id}"

    lines = [
        f"🏠 <b>{title}</b>",
        f"💰 {price:,} €".replace(",", " "),
        f"📐 {surface} m² — {rooms} pièces",
        f"📍 {city} ({zipcode})",
        f"🔗 {url}",
        "",
        "🟢 <i>Source: LeBonCoin (via GitHub Actions)</i>",
    ]
    return "\n".join(lines)


def matches_filters(ad: dict) -> bool:
    """Vérifie si l'annonce correspond aux filtres."""
    price_list = ad.get("price", [])
    price = int(price_list[0]) if price_list else 0
    if price == 0 or price > PRICE_MAX:
        return False

    attrs = {a["key"]: a.get("value", "") for a in ad.get("attributes", [])}
    surface_str = attrs.get("square", "0").replace("m²", "").strip() or "0"
    surface = int(surface_str)
    if surface < SURFACE_MIN:
        return False

    location = ad.get("location", {})
    zipcode = location.get("zipcode", "")
    if zipcode and zipcode not in TARGET_ZIPCODES:
        return False

    return True


def scrape():
    print(f"[START] Scan LeBonCoin via Playwright")
    print(f"[URL] {SEARCH_URL}")

    seen_ids = load_seen_ids()
    print(f"[CACHE] {len(seen_ids)} annonces déjà vues")

    api_data = None

    def capture_api(response):
        nonlocal api_data
        if "finder/search" in response.url and response.status == 200:
            try:
                api_data = response.json()
                print(f"[INTERCEPT] API response captured — {len(api_data.get('ads', []))} ads")
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="fr-FR",
            timezone_id="Europe/Paris",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )

        # Masquer les signaux d'automatisation
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR', 'fr', 'en-US', 'en']});
            window.chrome = {runtime: {}};
        """)

        page = context.new_page()
        page.on("response", capture_api)

        try:
            # Etape 1 : Visiter la homepage d'abord (cookies + warmup)
            print("[STEP 1] Visite homepage...")
            page.goto("https://www.leboncoin.fr/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # Accepter cookies si popup
            try:
                accept_btn = page.query_selector(
                    "button#didomi-notice-agree-button, "
                    "[class*='accept'], "
                    "[id*='accept']"
                )
                if accept_btn and accept_btn.is_visible():
                    accept_btn.click()
                    print("[COOKIES] Acceptés")
                    time.sleep(1)
            except Exception:
                pass

            # Etape 2 : Aller sur la page de recherche
            print("[STEP 2] Navigation vers la recherche...")
            page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)

            # Attendre que les résultats chargent (API interceptée)
            for i in range(15):
                if api_data:
                    break
                time.sleep(1)
                print(f"[WAIT] {i+1}s...")

            # Fallback : essayer de scroll pour déclencher le chargement
            if not api_data:
                print("[FALLBACK] Scroll pour forcer le chargement...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(3)

            page.screenshot(path="debug_screenshot.png")
            print(f"[SCREENSHOT] Sauvegardé")

        except Exception as e:
            print(f"[ERROR] Navigation: {e}")
            try:
                page.screenshot(path="debug_error.png")
            except Exception:
                pass

        browser.close()

    if not api_data:
        print("[FAIL] Aucune donnée API interceptée")
        # Essayer de lire les données depuis le HTML capturé ?
        return

    ads = api_data.get("ads", [])
    print(f"[RESULT] {len(ads)} annonces brutes")

    new_count = 0
    for ad in ads:
        ad_id = str(ad.get("list_id", ""))
        if not ad_id or ad_id in seen_ids:
            continue

        if not matches_filters(ad):
            seen_ids.add(ad_id)
            continue

        # Nouvelle annonce qui matche !
        seen_ids.add(ad_id)
        new_count += 1
        message = format_listing(ad)
        print(f"[NEW] {ad.get('subject', '?')} — {ad.get('price', ['?'])} €")
        send_telegram(message)

    save_seen_ids(seen_ids)
    print(f"[DONE] {new_count} nouvelles annonces envoyées, {len(seen_ids)} total en cache")


if __name__ == "__main__":
    scrape()
