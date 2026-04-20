"""SQLite — stockage et déduplication des annonces."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Listing:
    source: str          # leboncoin, bienici, pap, seloger
    source_id: str       # ID unique sur le site source
    title: str
    price: int           # en euros
    surface: int         # en m²
    rooms: int | None
    city: str
    zipcode: str
    url: str
    image_url: str = ""
    description: str = ""


class ListingDB:
    def __init__(self, db_path: str = "listings.db"):
        self._conn = sqlite3.connect(db_path)
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                price INTEGER NOT NULL,
                surface INTEGER NOT NULL,
                rooms INTEGER,
                city TEXT NOT NULL,
                zipcode TEXT NOT NULL,
                url TEXT NOT NULL,
                image_url TEXT DEFAULT '',
                description TEXT DEFAULT '',
                seen_at TEXT NOT NULL,
                notified INTEGER DEFAULT 0,
                UNIQUE(source, source_id)
            )
        """)
        self._conn.commit()

    def is_new(self, source: str, source_id: str) -> bool:
        cursor = self._conn.execute(
            "SELECT 1 FROM listings WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        return cursor.fetchone() is None

    def insert(self, listing: Listing) -> bool:
        """Insère une annonce. Retourne True si c'est une nouvelle annonce."""
        if not self.is_new(listing.source, listing.source_id):
            return False

        self._conn.execute(
            """INSERT INTO listings
               (source, source_id, title, price, surface, rooms,
                city, zipcode, url, image_url, description, seen_at, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                listing.source, listing.source_id, listing.title,
                listing.price, listing.surface, listing.rooms,
                listing.city, listing.zipcode, listing.url,
                listing.image_url, listing.description,
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()
        return True

    def mark_notified(self, source: str, source_id: str) -> None:
        self._conn.execute(
            "UPDATE listings SET notified = 1 WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        cursor = self._conn.execute(
            "SELECT source, COUNT(*) FROM listings GROUP BY source"
        )
        return dict(cursor.fetchall())

    def close(self) -> None:
        self._conn.close()
