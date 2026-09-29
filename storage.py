import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

class Storage:
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            conn.commit()

    def set_json(self, key: str, value: Dict[str, Any]):
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO kv(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False))
            )
            conn.commit()

    def get_json(self, key: str, default: Optional[Dict[str, Any]] = None):
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return json.loads(row["value"])

    def add_log(self, level: str, event: str, message: str, data: Optional[dict] = None):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO logs(created_at, level, event, message, data) VALUES(?,?,?,?,?)",
                (now, level, event, message, json.dumps(data or {}, ensure_ascii=False))
            )
            conn.commit()
            return cur.lastrowid

    def list_logs(self, limit: int = 100) -> List[dict]:
        limit = max(1, min(limit, 500))
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, created_at, level, event, message, data "
                "FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "created_at": r["created_at"],
                "level": r["level"],
                "event": r["event"],
                "message": r["message"],
                "data": json.loads(r["data"] or "{}")
            })
        return list(reversed(result))
