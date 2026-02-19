"""
MongoDB client and collection access.
Uses MONGODB_URI from environment (via .env) and database/collection names from config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from src.config_loader import get_mongodb_uri

if TYPE_CHECKING:
    pass


def get_client(uri: str | None = None) -> MongoClient:
    """
    Return a MongoDB client. Uses uri if provided, otherwise MONGODB_URI from environment.
    """
    if uri is None:
        uri = get_mongodb_uri()
    return MongoClient(uri)


def get_database(client: MongoClient, config: dict[str, Any]) -> Database:
    """Return the database from config (config['mongodb']['database'])."""
    name = (config.get("mongodb") or {}).get("database") or "pov_claims"
    return client[name]


def get_collection(client: MongoClient, config: dict[str, Any]) -> Collection:
    """
    Return the claims collection from config.
    Uses config['mongodb']['database'] and config['mongodb']['collection'].
    """
    db = get_database(client, config)
    coll_name = (config.get("mongodb") or {}).get("collection") or "claims"
    return db[coll_name]
