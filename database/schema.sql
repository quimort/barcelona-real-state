-- Raw landing table for scraped listings.
-- Same schema runs on local Docker Postgres and Supabase.

CREATE TABLE IF NOT EXISTS properties (
    id                 BIGSERIAL PRIMARY KEY,
    provider           TEXT        NOT NULL,
    url                TEXT        NOT NULL,
    price              TEXT,
    name               TEXT,
    size               TEXT,
    rooms              TEXT,
    bathrooms          TEXT,
    squere_meter_price TEXT,
    location           TEXT,
    description        TEXT,
    prop_type          TEXT,
    scraped_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- natural key: a listing URL is unique per provider
    CONSTRAINT uq_provider_url UNIQUE (provider, url)
);

CREATE INDEX IF NOT EXISTS idx_properties_provider  ON properties (provider);
CREATE INDEX IF NOT EXISTS idx_properties_location  ON properties (location);
CREATE INDEX IF NOT EXISTS idx_properties_scraped_at ON properties (scraped_at);
