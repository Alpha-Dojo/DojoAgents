from __future__ import annotations
from dojoagents.logging import LOGGER

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GatewaySession:
    key: str
    platform: str
    target: str
    user_id: str
    status: str = "idle"
    model_override: str | None = None
    reasoning_override: str | None = None
    resume_pending: bool = False
    updated_at: float = 0.0


class GatewaySessionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.sessions: dict[str, GatewaySession] = {}

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize DB and schema
        self._init_db()
        self.load()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrency and foreign key constraints
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        key TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        target TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        model_override TEXT,
                        reasoning_override TEXT,
                        resume_pending INTEGER NOT NULL DEFAULT 0,
                        updated_at REAL NOT NULL
                    )
                    """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS transcripts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_key TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        FOREIGN KEY (session_key) REFERENCES sessions(key) ON DELETE CASCADE
                    )
                    """)
        finally:
            conn.close()

    def load(self) -> None:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM sessions")
            rows = cursor.fetchall()
            self.sessions = {}
            for row in rows:
                self.sessions[row["key"]] = GatewaySession(
                    key=row["key"],
                    platform=row["platform"],
                    target=row["target"],
                    user_id=row["user_id"],
                    status=row["status"],
                    model_override=row["model_override"],
                    reasoning_override=row["reasoning_override"],
                    resume_pending=bool(row["resume_pending"]),
                    updated_at=row["updated_at"],
                )
        finally:
            conn.close()

    def save(self) -> None:
        conn = self._get_conn()
        try:
            with conn:
                for session in self.sessions.values():
                    conn.execute(
                        """
                        INSERT INTO sessions (
                            key, platform, target, user_id, status,
                            model_override, reasoning_override, resume_pending, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            status = excluded.status,
                            model_override = excluded.model_override,
                            reasoning_override = excluded.reasoning_override,
                            resume_pending = excluded.resume_pending,
                            updated_at = excluded.updated_at
                        """,
                        (
                            session.key,
                            session.platform,
                            session.target,
                            session.user_id,
                            session.status,
                            session.model_override,
                            session.reasoning_override,
                            1 if session.resume_pending else 0,
                            session.updated_at,
                        ),
                    )
        finally:
            conn.close()

    def get(self, key: str) -> GatewaySession:
        return self.sessions[key]

    def ensure(self, event: Any) -> GatewaySession:
        session = self.sessions.get(event.session_key)
        if session is None:
            session = GatewaySession(
                key=event.session_key,
                platform=event.platform,
                target=event.target,
                user_id=event.user_id,
            )
            self.sessions[event.session_key] = session
        session.updated_at = time.time()
        self.save()
        return session

    def set_status(self, key: str, status: str) -> None:
        if key in self.sessions:
            self.sessions[key].status = status
            self.sessions[key].updated_at = time.time()
            self.save()

    def set_model(self, key: str, model: str | None) -> None:
        if key in self.sessions:
            self.sessions[key].model_override = model
            self.sessions[key].updated_at = time.time()
            self.save()

    def clear(self, key: str) -> None:
        self.sessions.pop(key, None)
        conn = self._get_conn()
        try:
            with conn:
                conn.execute("DELETE FROM sessions WHERE key = ?", (key,))
        finally:
            conn.close()

    # --- Transcript / History Management ---

    def add_transcript(self, session_key: str, role: str, content: str) -> None:
        """Add a conversation message (user or assistant role) to transcripts table."""
        LOGGER.info(f"DEBUG: add_transcript called with session_key={session_key}, role={role}, content={content}")
        conn = self._get_conn()
        try:
            # Check if session exists in DB
            has_session = conn.execute("SELECT count(*) FROM sessions WHERE key = ?", (session_key,)).fetchone()[0]
            LOGGER.info(f"DEBUG: Before insert, session exists in DB: {has_session}")

            with conn:
                conn.execute(
                    """
                    INSERT INTO transcripts (session_key, role, content, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_key, role, content, time.time()),
                )
            LOGGER.info("DEBUG: INSERT successful!")

            # Check if transcripts row is visible immediately in the same connection
            count = conn.execute("SELECT count(*) FROM transcripts WHERE session_key = ?", (session_key,)).fetchone()[0]
            LOGGER.info(f"DEBUG: Immediately after insert, transcripts count for this session: {count}")
        except Exception as e:
            LOGGER.info(f"DEBUG: INSERT FAILED: {e}")
            raise
        finally:
            conn.close()

    def get_history(self, session_key: str, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve the last N turns for the session in chronological order."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT role, content FROM transcripts
                WHERE session_key = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (session_key, limit),
            )
            rows = cursor.fetchall()
            # Since we ordered DESC to apply the limit, reverse the results to restore chronological order
            history = [{"role": row["role"], "content": row["content"]} for row in rows]
            history.reverse()
            return history
        finally:
            conn.close()
