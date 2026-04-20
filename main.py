"""Bot immobilier — scanner des maisons en Val-de-Marne en temps réel."""

import sys
import traceback

print("=== IMMO-BOT STARTING ===", flush=True)

try:
    import logging
    import signal
    import time
    from datetime import datetime

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logger = logging.getLogger("immo-bot")

    print("Imports standard OK", flush=True)

    from config import CONFIG, CITIES, FILTERS
    print("Config OK", flush=True)

    from database import ListingDB
    print("Database OK", flush=True)

    from notifier import notify
    print("Notifier OK", flush=True)

    from scrapers import ALL_SCRAPERS
    print(f"Scrapers OK: {[s.name for s in ALL_SCRAPERS]}", flush=True)

    from server import start_health_server
    print("Server OK", flush=True)

except Exception as exc:
    print(f"IMPORT ERROR: {exc}", flush=True)
    traceback.print_exc()
    sys.exit(1)

# Arrêt propre
running = True


def signal_handler(signum, frame):
    global running
    logger.info("Signal %s reçu — arrêt...", signum)
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


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
    # Health check HTTP pour Render
    start_health_server()
    logger.info("Health server demarré")

    scrapers_str = ", ".join(s.name for s in ALL_SCRAPERS)
    logger.info("IMMO-BOT | %d EUR max | %dm2 min | Scrapers: %s", FILTERS.price_max, FILTERS.surface_min, scrapers_str)
    logger.info("Telegram: %s", "actif" if CONFIG.has_telegram else "inactif")

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
    try:
        main()
    except Exception as exc:
        print(f"FATAL ERROR: {exc}", flush=True)
        traceback.print_exc()
        sys.exit(1)
