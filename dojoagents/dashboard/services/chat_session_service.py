import json
from pathlib import Path
from typing import Any

from dojoagents.sessions.models import (
    HistoryQuery,
    SessionListQuery,
    SessionPrincipal,
    TurnQuery,
)
from dojoagents.sessions.service import SessionService

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
    def __init__(self, session_manager: Any, principal: SessionPrincipal | None = None):
        self.session_manager = session_manager
        self.principal = principal

    @property
    def canonical(self) -> bool:
        return self.principal is not None and self.canonical_backend

    @property
    def canonical_backend(self) -> bool:
        """Whether the wrapped manager implements the canonical session contract.

        This intentionally uses the concrete composition boundary instead of
        ``hasattr``. Test doubles and dynamic proxies commonly synthesize any
        requested attribute, which would otherwise route legacy managers into
        the canonical async API by accident.
        """

        return isinstance(self.session_manager, SessionService)

    def scoped(self, principal: SessionPrincipal) -> "ChatSessionService":
        return ChatSessionService(self.session_manager, principal)

    async def list_sessions(self, limit: int = 50, cursor: str | None = None, include_archived: bool = False) -> ChatSessionListResponse:
        if self.canonical:
            result = await self.session_manager.list_sessions(
                self.principal,
                SessionListQuery(archived=None if include_archived else False, limit=limit, cursor=cursor),
            )
            return ChatSessionListResponse(
                sessions=[self._canonical_summary(item) for item in result.items],
                next_cursor=result.next_cursor,
            )
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
        if self.canonical:
            try:
                return self._canonical_summary(await self.session_manager.get_session(self.principal, session_id))
            except Exception as exc:
                from dojoagents.sessions.errors import SessionNotFoundError

                if isinstance(exc, SessionNotFoundError):
                    return None
                raise
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
        if self.canonical:
            if await self.get_session(session_id) is None:
                return None
            result = await self.session_manager.history(self.principal, session_id, HistoryQuery(limit=limit))
            messages = [
                ChatSessionMessageResponse(
                    message_id=item.message_id,
                    role=item.role,
                    content=item.content if isinstance(item.content, str) else json.dumps(item.content, ensure_ascii=False),
                    created_at=item.created_at.isoformat(),
                    updated_at=item.created_at.isoformat(),
                    raw={},
                    raw_strands={},
                    openai_messages=[],
                )
                for item in result.items[offset:]
            ]
            return ChatSessionMessagesResponse(
                session_id=session_id,
                agent_id="dojo-agent",
                messages=messages,
                next_offset=None,
            )
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
        if self.canonical:
            result = await self.session_manager.turns(self.principal, session_id, TurnQuery(limit=200))
            return [
                {
                    "turn_id": item.turn_id,
                    "run_id": item.run_id,
                    "input": item.input,
                    "output": item.output,
                    "events": list(item.tool_trace),
                    "created_at": item.created_at.isoformat(),
                }
                for item in result.items
            ]
        return await self.session_manager.get_turns(session_id)

    async def archive_session(self, session_id: str) -> ArchiveChatSessionResponse | None:
        if self.canonical:
            current = await self.get_session(session_id)
            if current is None:
                return None
            record = await self.session_manager.get_session(self.principal, session_id)
            await self.session_manager.archive_session(self.principal, session_id, record.version)
            return ArchiveChatSessionResponse(archived=True, session_id=session_id)
        archived = await self.session_manager.archive_session(session_id)
        if not archived:
            return None
        return ArchiveChatSessionResponse(archived=True, session_id=session_id)

    async def export_sessions(self, request: ChatSessionExportRequest) -> ChatSessionExportResponse:
        if self.canonical:
            if not request.session_id:
                raise ValueError("canonical export requires session_id")
            payload = await self.session_manager.export_session(self.principal, request.session_id)
            export_dir = Path(request.output_dir or ".").expanduser().resolve()
            export_dir.mkdir(parents=True, exist_ok=True)
            target = export_dir / f"{request.session_id}.json"
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            messages = payload.get("history", {}).get("items", []) if isinstance(payload.get("history"), dict) else payload.get("history", [])
            return ChatSessionExportResponse(ok=True, export_dir=str(export_dir), session_count=1, message_count=len(messages), files=[str(target)])
        result = await self.session_manager.export_all(request.model_dump())
        return ChatSessionExportResponse(
            ok=result.ok,
            export_dir=result.export_dir,
            session_count=result.session_count,
            message_count=result.message_count,
            files=result.files,
        )

    @staticmethod
    def _canonical_summary(item: Any) -> ChatSessionSummaryResponse:
        return ChatSessionSummaryResponse(
            session_id=item.session_id,
            agent_id="dojo-agent",
            title=item.title,
            user_id=item.owner.user_id,
            channel=str(item.metadata.get("channel") or "dashboard"),
            model=item.model or "",
            locale=str(item.metadata.get("locale") or "zh"),
            created_at=item.created_at.isoformat(),
            updated_at=item.updated_at.isoformat(),
            message_count=item.message_count,
            turn_count=item.turn_count,
            run_count=0,
            status=item.status,
            archived=item.archived,
        )
