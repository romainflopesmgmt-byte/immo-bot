"""Configuration du bot immobilier — filtres, villes, paramètres."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class City:
    name: str
    zipcode: str
    department: str = "94"


# Villes ciblées dans le Val-de-Marne
CITIES: list[City] = [
    City("Saint-Maur-des-Fossés", "94100"),
    City("Saint-Maur-des-Fossés", "94210"),
    City("Chennevières-sur-Marne", "94430"),
    City("Joinville-le-Pont", "94340"),
    City("Bry-sur-Marne", "94360"),
    City("Le Perreux-sur-Marne", "94170"),
    City("Nogent-sur-Marne", "94130"),
    City("Le Plessis-Trévise", "94420"),
    City("Ormesson-sur-Marne", "94490"),
    City("Champigny-sur-Marne", "94500"),
]


@dataclass(frozen=True)
class SearchFilters:
    property_type: str = "house"       # house | apartment | both
    transaction: str = "buy"           # buy | rent
    price_max: int = 420_000           # € max
    price_min: int = 0                 # € min
    surface_min: int = 100             # m² min
    surface_max: int | None = None     # m² max (None = pas de limite)
    rooms_min: int | None = None       # pièces min
    rooms_max: int | None = None       # pièces max


FILTERS = SearchFilters()


@dataclass(frozen=True)
class BotConfig:
    # Intervalle entre les scans (en secondes)
    scan_interval: int = int(os.getenv("SCAN_INTERVAL", "180"))  # 3 min par défaut

    # Base de données
    db_path: str = os.getenv("DB_PATH", "listings.db")

    # Notifications — Free Mobile (gratuit)
    free_mobile_user: str = os.getenv("FREE_MOBILE_USER", "")
    free_mobile_pass: str = os.getenv("FREE_MOBILE_PASS", "")

    # Notifications — Twilio (payant ~0.04€/SMS)
    twilio_sid: str = os.getenv("TWILIO_SID", "")
    twilio_token: str = os.getenv("TWILIO_TOKEN", "")
    twilio_from: str = os.getenv("TWILIO_FROM", "")
    twilio_to: str = os.getenv("TWILIO_TO", "")

    # Notifications — Telegram (gratuit)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def has_free_mobile(self) -> bool:
        return bool(self.free_mobile_user and self.free_mobile_pass)

    @property
    def has_twilio(self) -> bool:
        return bool(self.twilio_sid and self.twilio_token and self.twilio_from and self.twilio_to)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


CONFIG = BotConfig()
