from typing import Any

from dojoagents.dashboard.schemas.chat_sessions import (
    ArchiveChatSessionResponse,
    ChatSessionExportRequest,
    ChatSessionExportResponse,
    ChatSessionListResponse,
    ChatSessionMessageResponse,
    ChatSessionMessagesResponse,
    ChatSessionSummaryResponse,
)


class ChatSessionService:
    def __init__(self, session_manager: Any):
        self.session_manager = session_manager

    async def list_sessions(self, limit: int = 50, cursor: str | None = None, include_archived: bool = False) -> ChatSessionListResponse:
        result = await self.session_manager.list_sessions(limit=limit, cursor=cursor, include_archived=include_archived)
        sessions = [
            ChatSessionSummaryResponse(
                session_id=item.session_id,
                agent_id=item.agent_id,
                title=item.title,
                user_id=item.user_id,
                channel=item.channel,
                model=item.model,
                locale=item.locale,
                created_at=item.created_at,
                updated_at=item.updated_at,
                message_count=item.message_count,
                turn_count=item.turn_count,
                run_count=item.run_count,
                last_run_id=item.last_run_id,
                status=item.status,
                archived=item.archived,
                token_state=item.token_state,
                memory_state=item.memory_state,
            )
            for item in result.sessions
        ]
        return ChatSessionListResponse(sessions=sessions, next_cursor=result.next_cursor)

    async def get_session(self, session_id: str) -> ChatSessionSummaryResponse | None:
        item = await self.session_manager.get_session(session_id)
        if item is None:
            return None
        return ChatSessionSummaryResponse(
            session_id=item.session_id,
            agent_id=item.agent_id,
            title=item.title,
            user_id=item.user_id,
            channel=item.channel,
            model=item.model,
            locale=item.locale,
            created_at=item.created_at,
            updated_at=item.updated_at,
            message_count=item.message_count,
            turn_count=item.turn_count,
            run_count=item.run_count,
            last_run_id=item.last_run_id,
            status=item.status,
            archived=item.archived,
            token_state=item.token_state,
            memory_state=item.memory_state,
        )

    async def get_messages(self, session_id: str, limit: int = 200, offset: int = 0) -> ChatSessionMessagesResponse | None:
        if await self.session_manager.get_session(session_id) is None:
            return None
        result = await self.session_manager.get_messages(session_id, limit=limit, offset=offset)
        messages = [
            ChatSessionMessageResponse(
                message_id=item.message_id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
                updated_at=item.updated_at,
                raw=item.raw,
                raw_strands=item.raw_strands,
                openai_messages=item.openai_messages,
            )
            for item in result.messages
        ]
        return ChatSessionMessagesResponse(
            session_id=result.session_id,
            agent_id=result.agent_id,
            messages=messages,
            next_offset=result.next_offset,
        )

    async def get_turns(self, session_id: str) -> list[dict[str, Any]]:
        return await self.session_manager.get_turns(session_id)

    async def archive_session(self, session_id: str) -> ArchiveChatSessionResponse | None:
        archived = await self.session_manager.archive_session(session_id)
        if not archived:
            return None
        return ArchiveChatSessionResponse(archived=True, session_id=session_id)

    async def export_sessions(self, request: ChatSessionExportRequest) -> ChatSessionExportResponse:
        result = await self.session_manager.export_all(request.model_dump())
        return ChatSessionExportResponse(
            ok=result.ok,
            export_dir=result.export_dir,
            session_count=result.session_count,
            message_count=result.message_count,
            files=result.files,
        )
