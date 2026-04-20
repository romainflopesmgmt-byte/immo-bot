"""Bot immobilier — scanner des maisons en Val-de-Marne en temps réel.

Scanne LeBonCoin, Bien'ici, PAP et SeLoger toutes les 3 minutes.
Envoie une notification SMS/Telegram pour chaque nouvelle annonce.
"""

import logging
import signal
import sys
import time
from datetime import datetime

from config import CONFIG, CITIES, FILTERS
from database import ListingDB
from notifier import notify
from scrapers import ALL_SCRAPERS
from server import start_health_server

# Logging
logging.basicConfig(
    level=getattr(logging, CONFIG.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("immo-bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("immo-bot")

# Arrêt propre
running = True


def signal_handler(signum, frame):
    global running
    logger.info("Signal %s reçu — arrêt en cours...", signum)
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def print_config() -> None:
    cities_str = ", ".join(f"{c.name} ({c.zipcode})" for c in CITIES)
    notif_channels = []
    if CONFIG.has_free_mobile:
        notif_channels.append("Free Mobile SMS")
    if CONFIG.has_twilio:
        notif_channels.append("Twilio SMS")
    if CONFIG.has_telegram:
        notif_channels.append("Telegram")
    if not notif_channels:
        notif_channels.append("AUCUN (configurez .env)")

    logger.info("=" * 60)
    logger.info("  IMMO-BOT — Scanner immobilier Val-de-Marne")
    logger.info("=" * 60)
    logger.info("  Villes    : %s", cities_str)
    logger.info("  Type      : %s", FILTERS.property_type)
    logger.info("  Prix max  : %s€", f"{FILTERS.price_max:,}")
    logger.info("  Surface   : >= %dm²", FILTERS.surface_min)
    logger.info("  Scan      : toutes les %ds (%dmin)", CONFIG.scan_interval, CONFIG.scan_interval // 60)
    logger.info("  Notifs    : %s", " + ".join(notif_channels))
    logger.info("  Sites     : LeBonCoin, Bien'ici, PAP, SeLoger")
    logger.info("=" * 60)


def run_scan(db: ListingDB) -> int:
    """Lance un scan sur tous les sites. Retourne le nombre de nouvelles annonces."""
    new_count = 0

    for scraper_class in ALL_SCRAPERS:
        scraper = scraper_class()
        try:
            listings = scraper.scrape()
            for listing in listings:
                if db.insert(listing):
                    new_count += 1
                    logger.info(
                        "NOUVELLE: [%s] %s — %s€ — %dm² — %s (%s)",
                        listing.source,
                        listing.title[:50],
                        f"{listing.price:,}",
                        listing.surface,
                        listing.city,
                        listing.url,
                    )
                    if notify(listing):
                        db.mark_notified(listing.source, listing.source_id)
        except Exception as exc:
            logger.error("Erreur scraper %s: %s", scraper.name, exc)
        finally:
            scraper.close()

    return new_count


def main() -> None:
    start_health_server()
    print_config()

    db = ListingDB(CONFIG.db_path)
    scan_number = 0

    try:
        while running:
            scan_number += 1
            start = time.monotonic()
            logger.info("--- Scan #%d à %s ---", scan_number, datetime.now().strftime("%H:%M:%S"))

            new_count = run_scan(db)
            elapsed = time.monotonic() - start

            stats = db.stats()
            total = sum(stats.values())
            logger.info(
                "Scan #%d terminé en %.1fs — %d nouvelles, %d total (%s)",
                scan_number,
                elapsed,
                new_count,
                total,
                ", ".join(f"{k}: {v}" for k, v in stats.items()),
            )

            # Attendre avant le prochain scan
            if running:
                logger.info("Prochain scan dans %ds...", CONFIG.scan_interval)
                # Dormir par tranches de 1s pour réagir vite au signal d'arrêt
                for _ in range(CONFIG.scan_interval):
                    if not running:
                        break
                    time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Interruption clavier")
    finally:
        db.close()
        logger.info("Bot arrêté proprement.")


if __name__ == "__main__":
    main()
