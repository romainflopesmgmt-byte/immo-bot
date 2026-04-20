"""Bot immobilier — scanner des maisons en Val-de-Marne en temps réel."""

import logging
import signal
import sys
import time
from datetime import datetime

# Logging en premier
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("immo-bot")

# Imports applicatifs
from config import CONFIG, CITIES, FILTERS
from database import ListingDB
from notifier import notify
from scrapers import ALL_SCRAPERS
from server import start_health_server

# Arrêt propre
running = True


def signal_handler(signum, frame):
    global running
    logger.info("Signal %s reçu — arrêt en cours...", signum)
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def print_config() -> None:
    notif_channels = []
    if CONFIG.has_free_mobile:
        notif_channels.append("Free Mobile SMS")
    if CONFIG.has_twilio:
        notif_channels.append("Twilio SMS")
    if CONFIG.has_telegram:
        notif_channels.append("Telegram")
    if not notif_channels:
        notif_channels.append("AUCUN")

    scrapers_str = ", ".join(s.name for s in ALL_SCRAPERS)
    logger.info("=" * 50)
    logger.info("  IMMO-BOT Val-de-Marne")
    logger.info("  Prix max: %d EUR | Surface min: %dm2", FILTERS.price_max, FILTERS.surface_min)
    logger.info("  Scan: toutes les %ds | Notifs: %s", CONFIG.scan_interval, " + ".join(notif_channels))
    logger.info("  Scrapers: %s", scrapers_str)
    logger.info("=" * 50)


def run_scan(db: ListingDB) -> int:
    new_count = 0
    for scraper_class in ALL_SCRAPERS:
        scraper = scraper_class()
        try:
            listings = scraper.scrape()
            for listing in listings:
                if db.insert(listing):
                    new_count += 1
                    logger.info(
                        "NOUVELLE: [%s] %s — %d EUR — %dm2 — %s",
                        listing.source, listing.title[:50],
                        listing.price, listing.surface, listing.city,
                    )
                    try:
                        notify(listing)
                        db.mark_notified(listing.source, listing.source_id)
                    except Exception as exc:
                        logger.error("Notification erreur: %s", exc)
        except Exception as exc:
            logger.error("Erreur scraper %s: %s", scraper.name, exc)
        finally:
            scraper.close()
    return new_count


def main() -> None:
    logger.info("Demarrage immo-bot...")

    # Serveur HTTP pour Render health check
    start_health_server()
    logger.info("Health server OK")

    print_config()

    db = ListingDB(CONFIG.db_path)
    scan_number = 0

    try:
        while running:
            scan_number += 1
            logger.info("--- Scan #%d ---", scan_number)

            try:
                new_count = run_scan(db)
                stats = db.stats()
                total = sum(stats.values()) if stats else 0
                logger.info("Scan #%d: %d nouvelles, %d total", scan_number, new_count, total)
            except Exception as exc:
                logger.error("Scan #%d erreur: %s", scan_number, exc)

            if running:
                for _ in range(CONFIG.scan_interval):
                    if not running:
                        break
                    time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        db.close()
        logger.info("Bot arrete.")


if __name__ == "__main__":
    main()
