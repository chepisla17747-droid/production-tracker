"""Build separate database pools without mixing their login details."""
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values
from psycopg_pool import ConnectionPool


DB_KEYS = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')


def read_database_config(path: Path) -> dict:
    # Read this file only; do not change shared environment variables.
    values = dict(dotenv_values(path, interpolate=False))
    missing = [key for key in DB_KEYS if not values.get(key)]
    if missing:
        raise ValueError(f"Missing database settings in {path.name}: {', '.join(missing)}")
    return values


def create_pool(settings: Mapping):
    """An unopened pool for one credential file's settings (never the process environment)."""
    # Passing values separately also handles spaces and quotes in passwords safely.
    return ConnectionPool(
        kwargs={
            'host': settings['DB_HOST'],
            'port': settings['DB_PORT'],
            'dbname': settings['DB_NAME'],
            'user': settings['DB_USER'],
            'password': settings['DB_PASSWORD'],
            'connect_timeout': 5,
        },
        min_size=1,
        max_size=10,
        open=False,
    )
