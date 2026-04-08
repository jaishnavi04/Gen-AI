# db.py — Database setup and helper functions
# Uses SQLite for lightweight, zero-config persistence

import sqlite3
import os
from datetime import datetime

DB_PATH = "assistant.db"


def get_connection():
    """Return a SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["title"]
    return conn


def init_db():
    """Create all tables if they don't already exist. Safe to call on startup."""
    conn = get_connection()
    cur = conn.cursor()

    # Tasks: things to do, with optional deadline and a status flag
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT    NOT NULL,
            status   TEXT    NOT NULL DEFAULT 'pending',   -- pending | done
            deadline TEXT,                                 -- ISO date string, optional
            created  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Notes: free-form text blobs, tagged with a timestamp
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            content  TEXT NOT NULL,
            created  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Calendar events: scheduled items with a title and datetime
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            event_time TEXT NOT NULL,   -- ISO datetime string
            created    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Conversation memory: stores the last N exchanges per session
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            role      TEXT NOT NULL,     -- 'user' or 'assistant'
            content   TEXT NOT NULL,
            session   TEXT NOT NULL DEFAULT 'default',
            created   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print(f"[db] Database ready at '{DB_PATH}'")


# ── Conversation memory helpers ───────────────────────────────────────────────

def save_message(role: str, content: str, session: str = "default"):
    """Persist a single chat turn."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (role, content, session) VALUES (?, ?, ?)",
        (role, content, session)
    )
    conn.commit()
    conn.close()


def get_history(session: str = "default", limit: int = 10) -> list[dict]:
    """Retrieve the most recent `limit` turns for a session (oldest first)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT role, content FROM conversations
           WHERE session = ?
           ORDER BY id DESC LIMIT ?""",
        (session, limit)
    ).fetchall()
    conn.close()
    # Reverse so oldest is first (correct order for LLM context)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
