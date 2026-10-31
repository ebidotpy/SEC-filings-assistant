from datetime import datetime
from uuid import UUID

from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.router import protected_router
from app.auth.dependencies import CurrentUser
from app.chat.messages import StreamChatRequest, ui_message_from_row
from app.chat.orchestrator import require_owned_thread, run_grounded_turn
from app.chat.streaming import STREAM_HEADERS
from app.database.chats import create_thread, list_messages, list_threads
from app.database.users import ensure_app_user

router = protected_router


class CreateThreadRequest(BaseModel):
    title: str | None = None


class ThreadSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


def _thread_summary(thread) -> ThreadSummary:
    return ThreadSummary(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("/chat/threads", tags=["chat"])
async def get_threads(user: CurrentUser) -> list[ThreadSummary]:
    await ensure_app_user(user.id, user.email)
    threads = await list_threads(user.id)
    return [_thread_summary(thread) for thread in threads]


@router.post("/chat/threads", tags=["chat"])
async def post_thread(
    user: CurrentUser,
    body: CreateThreadRequest | None = None,
) -> ThreadSummary:
    await ensure_app_user(user.id, user.email)
    title = body.title if body and body.title else "New chat"
    thread = await create_thread(user.id, title=title)
    return _thread_summary(thread)


@router.get("/chat/threads/{thread_id}/messages", tags=["chat"])
async def get_thread_messages(
    thread_id: UUID,
    user: CurrentUser,
) -> list[dict]:
    await require_owned_thread(thread_id, user.id)
    messages = await list_messages(thread_id)
    return [ui_message_from_row(message) for message in messages]


@router.post("/chat/stream", tags=["chat"])
async def post_chat_stream(
    body: StreamChatRequest,
    user: CurrentUser,
) -> StreamingResponse:
    generator = run_grounded_turn(user, body.thread_id, body.messages)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
