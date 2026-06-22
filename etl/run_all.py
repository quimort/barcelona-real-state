"""Orchestrator: scrape every provider and load results into Postgres.

Run locally:    pipenv run python etl/run_all.py
Run one:        pipenv run python etl/run_all.py --only habitaclia

Each provider is isolated — a failure in one does not stop the others.
"""

import argparse
import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from components.etl_components.loader import load_properties
from components.etl_components.property import Property
from components.etl_components.provider import Provider
from etl.extraction.fotocasa import FotocasaProvider
from etl.extraction.habitaclia import HabitacliaProvider
from etl.extraction.idealista import IdealistaProvider

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, type[Provider]] = {
    "habitaclia": HabitacliaProvider,
    "idealista": IdealistaProvider,
    "fotocasa": FotocasaProvider,
}


def run_provider(name: str, provider_cls: type[Provider], limit: int | None = None) -> int:
    logger.info("=== Running provider: %s ===", name)
    try:
        properties: list[Property] = provider_cls().run(max_properties=limit)  # type: ignore[call-arg]
        written = load_properties(properties)
        logger.info("%s: %d properties loaded", name, written)
        return written
    except Exception:
        logger.exception("%s failed — continuing with remaining providers", name)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Barcelona real estate scrapers")
    parser.add_argument("--only", choices=PROVIDERS.keys(), help="Run a single provider")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap number of properties scraped per provider (smoke-test mode)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    selected = {args.only: PROVIDERS[args.only]} if args.only else PROVIDERS

    total = 0
    for name, cls in selected.items():
        total += run_provider(name, cls, limit=args.limit)
    logger.info("Done. Total properties loaded across providers: %d", total)


if __name__ == "__main__":
    main()
