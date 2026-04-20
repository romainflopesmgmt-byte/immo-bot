"""Notifications — SMS (Free Mobile / Twilio) + Telegram."""

import logging
import urllib.parse

import httpx

from config import CONFIG
from database import Listing

logger = logging.getLogger(__name__)


def format_message(listing: Listing) -> str:
    rooms_str = f"{listing.rooms}p" if listing.rooms else "?"
    return (
        f"🏠 NOUVELLE ANNONCE\n"
        f"{listing.title}\n"
        f"💰 {listing.price:,}€ | {listing.surface}m² | {rooms_str}\n"
        f"📍 {listing.city} ({listing.zipcode})\n"
        f"🔗 {listing.url}\n"
        f"📡 {listing.source}"
    )


def send_free_mobile(message: str) -> bool:
    """SMS gratuit via l'API Free Mobile (abonnés Free uniquement)."""
    if not CONFIG.has_free_mobile:
        return False

    try:
        encoded = urllib.parse.quote(message[:999])
        resp = httpx.get(
            "https://smsapi.free-mobile.fr/sendmsg",
            params={
                "user": CONFIG.free_mobile_user,
                "pass": CONFIG.free_mobile_pass,
                "msg": message[:999],
            },
            timeout=15,
        )
        if resp.status_code == 200:
            logger.info("SMS Free Mobile envoyé")
            return True
        logger.warning("Free Mobile HTTP %s", resp.status_code)
        return False
    except httpx.HTTPError as exc:
        logger.error("Free Mobile erreur: %s", exc)
        return False


def send_twilio(message: str) -> bool:
    """SMS payant via Twilio (~0.04€/SMS France)."""
    if not CONFIG.has_twilio:
        return False

    try:
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{CONFIG.twilio_sid}/Messages.json",
            auth=(CONFIG.twilio_sid, CONFIG.twilio_token),
            data={
                "From": CONFIG.twilio_from,
                "To": CONFIG.twilio_to,
                "Body": message[:1600],
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            logger.info("SMS Twilio envoyé")
            return True
        logger.warning("Twilio HTTP %s: %s", resp.status_code, resp.text[:200])
        return False
    except httpx.HTTPError as exc:
        logger.error("Twilio erreur: %s", exc)
        return False


def send_telegram(message: str) -> bool:
    """Message Telegram gratuit via Bot API."""
    if not CONFIG.has_telegram:
        return False

    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{CONFIG.telegram_bot_token}/sendMessage",
            json={
                "chat_id": CONFIG.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            logger.info("Telegram envoyé")
            return True
        logger.warning("Telegram HTTP %s", resp.status_code)
        return False
    except httpx.HTTPError as exc:
        logger.error("Telegram erreur: %s", exc)
        return False


def notify(listing: Listing) -> bool:
    """Envoie la notification via tous les canaux configurés.
    Retourne True si au moins un canal a réussi."""
    message = format_message(listing)
    sent = False

    if CONFIG.has_free_mobile:
        sent = send_free_mobile(message) or sent

    if CONFIG.has_twilio:
        sent = send_twilio(message) or sent

    if CONFIG.has_telegram:
        sent = send_telegram(message) or sent

    if not sent:
        logger.warning(
            "Aucun canal de notification configuré ou tous ont échoué. "
            "Configurez FREE_MOBILE_*, TWILIO_*, ou TELEGRAM_* dans .env"
        )

    return sent
