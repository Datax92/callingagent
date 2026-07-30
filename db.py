"""
MongoDB connection lifecycle. Isolated so app.py just calls `lifespan`.
"""
from contextlib import asynccontextmanager

import certifi
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_settings = Settings()

    client = AsyncIOMotorClient(
        app_settings.mongodb_uri,
        tls=True,
        tlsCAFile=certifi.where(),
    )
    db = client[app_settings.mongodb_database]
    calls = db["calls"]

    await calls.create_index("created_at")
    await calls.create_index("status")
    await calls.create_index("caller_number")
    await calls.create_index("call_direction")
    await calls.create_index("room_name")

    app.state.settings = app_settings
    app.state.mongo_client = client
    app.state.calls = calls
    try:
        yield
    finally:
        client.close()
