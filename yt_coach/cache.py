"""SQLite JSON cache with per-entry TTL."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, path: Path | str, default_ttl: int = 12 * 3600):
        self.default_ttl = default_ttl
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)"
        )
        self._db.commit()

    def get(self, key: str) -> Any | None:
        row = self._db.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        if row[1] < time.time():
            self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._db.commit()
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        exp = time.time() + (self.default_ttl if ttl is None else ttl)
        self._db.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), exp),
        )
        self._db.commit()

    def purge_expired(self) -> int:
        cur = self._db.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))
        self._db.commit()
        return cur.rowcount
