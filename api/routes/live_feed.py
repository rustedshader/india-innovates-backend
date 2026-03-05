"""WebSocket route — live article ingestion feed via Redis Pub/Sub."""

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import REDIS_HOST, REDIS_PORT

logger = logging.getLogger(__name__)

router = APIRouter()

REDIS_CHANNEL = "india-innovates:live-feed"


@router.websocket("/ws/live-feed")
async def live_feed(websocket: WebSocket):
    """Stream real-time article ingestion events to connected clients.

    Each message is JSON: {url, title, source, thumbnail, pub_date, status, timestamp}
    """
    await websocket.accept()

    r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)

    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message["type"] == "message":
                try:
                    await websocket.send_text(message["data"])
                except WebSocketDisconnect:
                    break
            else:
                # Yield control to check for client disconnect
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL)
        await pubsub.close()
        await r.close()
        logger.debug("WebSocket client disconnected from live feed")
