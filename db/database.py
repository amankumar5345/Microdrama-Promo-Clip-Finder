"""
db/database.py
──────────────
SQLite persistence layer for Microdrama Promo Clip Finder.
Stores sessions, extracted clips, user favorites, feedback, and interactive chat history.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Optional
import uuid

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "outputs" / "promo_history.db"


class PromoDatabase:
    """Manages SQLite operations for sessions, clips, feedback, and Q&A chat history."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self):
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    script_text TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settings_json TEXT,
                    report_md TEXT
                );

                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    clip_id TEXT NOT NULL,
                    start_s REAL NOT NULL,
                    end_s REAL NOT NULL,
                    duration_sec REAL NOT NULL,
                    start_fmt TEXT NOT NULL,
                    end_fmt TEXT NOT NULL,
                    total_score REAL NOT NULL,
                    hook_score REAL NOT NULL,
                    cliffhanger_score REAL NOT NULL,
                    emotion_score REAL NOT NULL,
                    standalone_score REAL NOT NULL,
                    hook_line TEXT,
                    hook_type TEXT,
                    cliffhanger_line TEXT,
                    why_it_works TEXT,
                    problems_json TEXT,
                    standalone_test_json TEXT,
                    raw_data_json TEXT,
                    is_favorite INTEGER DEFAULT 0,
                    user_feedback INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_clips_session ON clips (session_id);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id);
            """)

    # ── Sessions ─────────────────────────────────────────────────────────────

    def create_session(
        self,
        title: str,
        filename: str,
        script_text: str,
        mode: str,
        settings: Optional[dict] = None,
        report_md: str = "",
        session_id: Optional[str] = None,
    ) -> str:
        """Create a new run session."""
        sid = session_id or str(uuid.uuid4())[:8]
        settings_str = json.dumps(settings or {}, ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, title, filename, script_text, mode, settings_json, report_md)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sid, title, filename, script_text, mode, settings_str, report_md)
            )
        return sid

    def get_sessions(self, limit: int = 50) -> list[dict]:
        """Fetch past sessions ordered by most recent."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.filename, s.mode, s.created_at,
                       COUNT(c.id) as clip_count
                FROM sessions s
                LEFT JOIN clips c ON s.id = c.session_id
                GROUP BY s.id
                ORDER BY s.created_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> Optional[dict]:
        """Fetch session metadata by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["settings"] = json.loads(data.get("settings_json") or "{}")
            return data

    def update_session_title(self, session_id: str, new_title: str):
        """Rename a session."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (new_title, session_id)
            )

    def delete_session(self, session_id: str):
        """Delete a session and all its clips and chat messages."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # ── Clips ────────────────────────────────────────────────────────────────

    def save_clips(self, session_id: str, ranked_clips: list[dict]):
        """Persist ranked promo clips for a session."""
        with self._get_connection() as conn:
            for c in ranked_clips:
                conn.execute(
                    """
                    INSERT INTO clips (
                        session_id, clip_id, start_s, end_s, duration_sec,
                        start_fmt, end_fmt, total_score, hook_score, cliffhanger_score,
                        emotion_score, standalone_score, hook_line, hook_type,
                        cliffhanger_line, why_it_works, problems_json,
                        standalone_test_json, raw_data_json, is_favorite, user_feedback
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        c["clip_id"],
                        c.get("start_s", c.get("_start_s", 0.0)),
                        c.get("end_s", c.get("_end_s", 0.0)),
                        c.get("duration_sec", 0.0),
                        c.get("start_fmt", ""),
                        c.get("end_fmt", ""),
                        c.get("total_score", 0.0),
                        c.get("hook", 0.0),
                        c.get("cliffhanger", 0.0),
                        c.get("emotion", 0.0),
                        c.get("standalone", 0.0),
                        c.get("hook_line", ""),
                        c.get("hook_type", ""),
                        c.get("cliffhanger_line", ""),
                        c.get("why_it_works", ""),
                        json.dumps(c.get("problems", []), ensure_ascii=False),
                        json.dumps(c.get("standalone_test", {}), ensure_ascii=False),
                        json.dumps(c, ensure_ascii=False),
                        1 if c.get("is_favorite") else 0,
                        c.get("user_feedback", 0),
                    )
                )

    def get_clips(self, session_id: str) -> list[dict]:
        """Retrieve all clips belonging to a session."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM clips WHERE session_id = ? ORDER BY total_score DESC",
                (session_id,)
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["problems"] = json.loads(item.get("problems_json") or "[]")
                item["standalone_test"] = json.loads(item.get("standalone_test_json") or "{}")
                item["hook"] = item["hook_score"]
                item["cliffhanger"] = item["cliffhanger_score"]
                item["emotion"] = item["emotion_score"]
                item["standalone"] = item["standalone_score"]
                item["is_favorite"] = bool(item.get("is_favorite", 0))
                results.append(item)
            return results

    def toggle_favorite(self, clip_id: str, session_id: str) -> bool:
        """Toggle favorite star state for a clip."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT is_favorite FROM clips WHERE clip_id = ? AND session_id = ?",
                (clip_id, session_id)
            ).fetchone()
            if not row:
                return False
            new_val = 0 if row["is_favorite"] else 1
            conn.execute(
                "UPDATE clips SET is_favorite = ? WHERE clip_id = ? AND session_id = ?",
                (new_val, clip_id, session_id)
            )
            return bool(new_val)

    def set_feedback(self, clip_id: str, session_id: str, feedback: int):
        """Set user thumbs-up (1), thumbs-down (-1), or neutral (0)."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE clips SET user_feedback = ? WHERE clip_id = ? AND session_id = ?",
                (feedback, clip_id, session_id)
            )

    def update_clip_times(
        self,
        clip_id: str,
        session_id: str,
        new_start_s: float,
        new_end_s: float,
        start_fmt: str,
        end_fmt: str,
    ):
        """Update fine-tuned start and end timestamps."""
        new_dur = max(0.0, new_end_s - new_start_s)
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE clips
                SET start_s = ?, end_s = ?, duration_sec = ?, start_fmt = ?, end_fmt = ?
                WHERE clip_id = ? AND session_id = ?
                """,
                (new_start_s, new_end_s, new_dur, start_fmt, end_fmt, clip_id, session_id)
            )

    # ── Chat Messages ────────────────────────────────────────────────────────

    def add_message(self, session_id: str, role: str, content: str):
        """Append a chat message to a session."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )

    def get_messages(self, session_id: str) -> list[dict]:
        """Fetch chat history for a session."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            ).fetchall()
            return [dict(r) for r in rows]


_DB_INSTANCE: Optional[PromoDatabase] = None


def get_db() -> PromoDatabase:
    """Singleton getter for the SQLite database."""
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        _DB_INSTANCE = PromoDatabase()
    return _DB_INSTANCE
