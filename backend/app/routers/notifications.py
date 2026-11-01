import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import notify
from ..config import get_settings
from ..deps import Principal, current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: Principal = Depends(current_user), limit: int = Query(50, ge=1, le=200)):
    return {"notifications": notify.list_notifications(user.id, user.is_staff, limit),
            "unread": notify.unread_count(user.id, user.is_staff)}


@router.get("/unread-count")
def unread(user: Principal = Depends(current_user)):
    return {"unread": notify.unread_count(user.id, user.is_staff)}


@router.post("/read-all")
def read_all(user: Principal = Depends(current_user)):
    return {"updated": notify.mark_read(user.id, user.is_staff)}


@router.post("/{notification_id}/read")
def read_one(notification_id: str, user: Principal = Depends(current_user)):
    return {"updated": notify.mark_read(user.id, user.is_staff, notification_id)}


@router.delete("/{notification_id}")
def delete_one(notification_id: str, user: Principal = Depends(current_user)):
    try:
        deleted = notify.delete_notification(user.id, notification_id)
    except Exception:  # malformed ObjectId
        raise HTTPException(404, "Notification not found")
    if not deleted:
        raise HTTPException(404, "Notification not found")
    return {"deleted": deleted}


@router.get("/stream")
async def stream(user: Principal = Depends(current_user)):
    """Server-sent events fed by Redis pub/sub (published by the outbox worker)."""
    channels = [f"lf:notify:user:{user.id}"] + (["lf:notify:staff"] if user.is_staff else [])

    async def gen():
        client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(*channels)
        try:
            yield "retry: 3000\n\n"
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    yield ": keep-alive\n\n"
                else:
                    yield f"event: notification\ndata: {msg['data']}\n\n"
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe()
            await client.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
