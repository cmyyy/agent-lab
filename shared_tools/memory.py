"""memory.py —— SQLite 记忆（FR-3，纯标准库零依赖）。

设计（PRD FR-3）：
- 记忆（应用数据：会话/笔记/经验）与观测（遥测数据）同一 agent.db 不同 schema 分组
- v1.0 用结构化查询（按时间/标签），不上 embedding 记忆检索
- 经验表预留 status 字段（pending/approved）——FR-7 自进化直接复用
- save_note/read_note 的相对路径 bug 修正：统一走本项目 DB（不再写 ./notes）

表结构：
  sessions  会话（id, created_at, last_active）
  notes     笔记（title, content, created_at）—— save_note/read_note 的落点
  messages  消息（session_id, role, content, created_at）—— 多轮对话持久化
  experiences 经验（id, pattern, solution, source_evidence, status(pending/approved), created_at）
"""

import os
import sqlite3
import time
from pathlib import Path

# agent.db 位置：项目根（不进 git——.gitignore 排除 *.db）
_DB_PATH = Path(__file__).resolve().parent.parent / "agent.db"


def _connect():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None) -> None:
    """建表（幂等）。"""
    global _DB_PATH
    if db_path:
        _DB_PATH = Path(db_path)
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at REAL,
                last_active REAL
            );
            CREATE TABLE IF NOT EXISTS notes (
                title TEXT PRIMARY KEY,
                content TEXT,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT,
                solution TEXT,
                source_evidence TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# -- 会话 ---------------------------------------------------------------

def upsert_session(session_id: str) -> None:
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO sessions(id, created_at, last_active) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET last_active=?",
            (session_id, now, now, now),
        )
        conn.commit()
    finally:
        conn.close()


# -- 笔记（save_note / read_note 的落点，修正相对路径 bug）-----------------

def save_note(title: str, content: str) -> dict:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO notes(title, content, created_at) VALUES(?,?,?) "
            "ON CONFLICT(title) DO UPDATE SET content=excluded.content",
            (title, content, time.time()),
        )
        conn.commit()
        return {"status": "ok", "title": title}
    except Exception as e:
        return {"error": f"保存笔记失败: {e}"}
    finally:
        conn.close()


def read_note(title: str) -> dict:
    conn = _connect()
    try:
        row = conn.execute("SELECT title, content FROM notes WHERE title=?", (title,)).fetchone()
        if row is None:
            return {"error": f"未找到笔记: {title}"}
        return {"title": row["title"], "content": row["content"]}
    finally:
        conn.close()


# -- 消息（多轮对话持久化，FR-3）------------------------------------------

def append_message(session_id: str, role: str, content: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
            (session_id, role, content, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def load_history(session_id: str, limit: int = 50) -> list[dict]:
    """读回会话历史（跨会话可用：新会话能读旧会话的笔记/消息）。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    finally:
        conn.close()


# -- 经验（FR-7 自进化复用，status 字段预留）--------------------------------

def add_experience(pattern: str, solution: str, source_evidence: str = "") -> int:
    """新增经验（默认 pending，人工审批后转 approved——FR-7 human-in-the-loop）。"""
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO experiences(pattern, solution, source_evidence, status, created_at) VALUES(?,?,?,?,?)",
            (pattern, solution, source_evidence, "pending", time.time()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def approve_experience(exp_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE experiences SET status='approved' WHERE id=?", (exp_id,))
        conn.commit()
    finally:
        conn.close()


def get_approved_experiences() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM experiences WHERE status='approved'").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
