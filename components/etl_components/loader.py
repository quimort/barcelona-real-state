import logging
from collections.abc import Iterable

import psycopg2
from psycopg2.extras import execute_values

from .config import get_database_url
from .property import Property

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO properties (
    provider, url, price, name, size, rooms, bathrooms,
    squere_meter_price, location, description, prop_type, scraped_at
)
VALUES %s
ON CONFLICT (provider, url) DO UPDATE SET
    price              = EXCLUDED.price,
    name               = EXCLUDED.name,
    size               = EXCLUDED.size,
    rooms              = EXCLUDED.rooms,
    bathrooms          = EXCLUDED.bathrooms,
    squere_meter_price = EXCLUDED.squere_meter_price,
    location           = EXCLUDED.location,
    description        = EXCLUDED.description,
    prop_type          = EXCLUDED.prop_type,
    scraped_at         = EXCLUDED.scraped_at;
"""


def _to_row(p: Property) -> tuple:
    return (
        p.provider,
        p.url,
        p.price,
        p.name,
        p.size,
        p.rooms,
        p.bathrooms,
        p.squere_meter_price,
        p.location,
        p.description,
        p.prop_type,
        p.scraped_at,
    )


def load_properties(properties: Iterable[Property], database_url: str | None = None) -> int:
    """Upsert properties into Postgres. Returns the number of rows written.

    Idempotent on (provider, url): re-scraping a listing refreshes it in place
    rather than creating duplicates.
    """
    rows = [_to_row(p) for p in properties]
    if not rows:
        logger.info("No properties to load")
        return 0

    dsn = database_url or get_database_url()
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            execute_values(cur, _UPSERT_SQL, rows)
        conn.commit()

    logger.info("Loaded %d properties", len(rows))
    return len(rows)
