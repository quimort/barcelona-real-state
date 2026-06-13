from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Property:
    """Shared output contract for every provider scraper.

    `url` together with `provider` forms the natural dedup/upsert key.
    """

    price: str
    name: str
    size: str
    rooms: str
    bathrooms: str
    squere_meter_price: str
    location: str
    description: str
    prop_type: str
    provider: str
    url: str = ""
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
