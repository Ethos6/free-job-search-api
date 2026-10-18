"""SQLite storage: the local job index (with full-text search), known company job boards,
and saved searches (alerts)."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from .models import Job

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS boards (
    ats TEXT NOT NULL,
    token TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL DEFAULT 'seed',
    added REAL NOT NULL,
    last_fetched REAL NOT NULL DEFAULT 0,
    last_ok REAL NOT NULL DEFAULT 0,
    job_count INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ats, token)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,        -- also the rowid of the job's full-text entry
    key TEXT NOT NULL UNIQUE,
    origin TEXT NOT NULL,          -- 'greenhouse:stripe' or 'feed:remotive'
    data TEXT NOT NULL,            -- Job as JSON
    posted REAL,
    fetched REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_origin ON jobs(origin);
CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    title, company, location, tags, body,
    tokenize = "unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    every_hours REAL NOT NULL,
    webhook TEXT,
    created REAL NOT NULL,
    last_run REAL NOT NULL DEFAULT 0,
    next_run REAL NOT NULL,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS alert_hits (
    alert_id TEXT NOT NULL,
    job_key TEXT NOT NULL,
    seen REAL NOT NULL,
    data TEXT NOT NULL,            -- Match as JSON, for the RSS feed
    PRIMARY KEY (alert_id, job_key)
);
CREATE INDEX IF NOT EXISTS alert_hits_time ON alert_hits(alert_id, seen);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[None]:
        with self._lock:
            if self._db.in_transaction:
                yield
                return
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _exec(self, sql: str, args: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, args)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- meta ------------------------------------------------------------------------------------
    def get_meta(self, k: str, default: str = "") -> str:
        row = self._exec("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row["v"] if row else default

    def set_meta(self, k: str, v: str) -> None:
        self._exec("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

    # -- boards ----------------------------------------------------------------------------------
    def add_board(self, ats: str, token: str, company: str = "", added_by: str = "seed") -> bool:
        token = token.strip()
        if not token or len(token) > 120 or not re.fullmatch(r"[A-Za-z0-9._\-]+", token):
            return False
        cur = self._exec("INSERT OR IGNORE INTO boards(ats,token,company,added_by,added) VALUES(?,?,?,?,?)",
                         (ats, token, company, added_by, time.time()))
        return cur.rowcount > 0

    def boards(self, ats: Optional[str] = None) -> list[dict[str, Any]]:
        if ats:
            rows = self._exec("SELECT * FROM boards WHERE ats=? ORDER BY token", (ats,))
        else:
            rows = self._exec("SELECT * FROM boards ORDER BY ats, token")
        return [dict(r) for r in rows]

    def due_boards(self, older_than: float, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._exec("SELECT * FROM boards WHERE last_fetched < ? AND failures < 6 "
                          "ORDER BY last_fetched ASC LIMIT ?", (older_than, limit))
        return [dict(r) for r in rows]

    def board_done(self, ats: str, token: str, ok: bool, job_count: int = 0, company: str = "") -> None:
        now = time.time()
        if ok:
            self._exec("UPDATE boards SET last_fetched=?, last_ok=?, job_count=?, failures=0, "
                       "company=CASE WHEN ?<>'' THEN ? ELSE company END WHERE ats=? AND token=?",
                       (now, now, job_count, company, company, ats, token))
        else:
            self._exec("UPDATE boards SET last_fetched=?, failures=failures+1 WHERE ats=? AND token=?",
                       (now, ats, token))

    # -- jobs index ------------------------------------------------------------------------------
    def replace_jobs(self, origin: str, jobs: list[Job]) -> int:
        """Replace everything indexed from one board or feed with its current jobs."""
        now = time.time()
        with self.tx():
            self._exec("DELETE FROM jobs_fts WHERE rowid IN (SELECT id FROM jobs WHERE origin=?)", (origin,))
            self._exec("DELETE FROM jobs WHERE origin=?", (origin,))
            seen = set()
            for j in jobs:
                key = j.key()
                if key in seen or not j.url or not j.title:
                    continue
                seen.add(key)
                cur = self._exec("INSERT OR IGNORE INTO jobs(key,origin,data,posted,fetched) VALUES(?,?,?,?,?)",
                                 (key, origin, j.model_dump_json(),
                                  j.posted_at.timestamp() if j.posted_at else None, now))
                if not cur.rowcount:
                    continue  # the same job is already indexed from another origin
                self._exec("INSERT INTO jobs_fts(rowid,title,company,location,tags,body) VALUES(?,?,?,?,?,?)",
                           (cur.lastrowid, j.title, j.company, j.location, " ".join(j.tags), j.description[:6000]))
        return len(seen)

    def search_jobs(self, fts_query: str, limit: int = 1500) -> list[Job]:
        if not fts_query:
            return []
        try:
            rows = self._exec(
                "SELECT j.data FROM jobs_fts f JOIN jobs j ON j.id=f.rowid WHERE jobs_fts MATCH ? "
                "ORDER BY bm25(jobs_fts, 10.0, 3.0, 2.0, 2.0, 1.0) LIMIT ?", (fts_query, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [Job.model_validate_json(r["data"]) for r in rows]

    def job_count(self) -> int:
        return self._exec("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def prune_jobs(self, older_than_days: float = 120) -> int:
        cutoff = time.time() - older_than_days * 86400
        with self.tx():
            self._exec("DELETE FROM jobs_fts WHERE rowid IN (SELECT id FROM jobs WHERE fetched < ?)", (cutoff,))
            return self._exec("DELETE FROM jobs WHERE fetched < ?", (cutoff,)).rowcount

    # -- alerts ----------------------------------------------------------------------------------
    def add_alert(self, alert_id: str, token_hash: str, text: str, every_hours: float,
                  webhook: Optional[str]) -> None:
        now = time.time()
        self._exec("INSERT INTO alerts(id,token_hash,text,every_hours,webhook,created,next_run) "
                   "VALUES(?,?,?,?,?,?,?)", (alert_id, token_hash, text, every_hours, webhook, now, now))

    def alert(self, alert_id: str) -> Optional[dict[str, Any]]:
        row = self._exec("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        return dict(row) if row else None

    def alerts_count(self) -> int:
        return self._exec("SELECT COUNT(*) FROM alerts").fetchone()[0]

    def due_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._exec("SELECT * FROM alerts WHERE next_run <= ? ORDER BY next_run LIMIT ?",
                          (time.time(), limit))
        return [dict(r) for r in rows]

    def alert_ran(self, alert_id: str, every_hours: float, error: Optional[str] = None) -> None:
        now = time.time()
        self._exec("UPDATE alerts SET last_run=?, next_run=?, last_error=? WHERE id=?",
                   (now, now + every_hours * 3600, error, alert_id))

    def delete_alert(self, alert_id: str) -> bool:
        with self.tx():
            self._exec("DELETE FROM alert_hits WHERE alert_id=?", (alert_id,))
            return self._exec("DELETE FROM alerts WHERE id=?", (alert_id,)).rowcount > 0

    def new_hits(self, alert_id: str, matches: list[tuple[str, str]]) -> list[str]:
        """Record matches (key, json) and return the keys that were not seen before."""
        now = time.time()
        fresh = []
        with self.tx():
            for key, data in matches:
                cur = self._exec("INSERT OR IGNORE INTO alert_hits(alert_id,job_key,seen,data) VALUES(?,?,?,?)",
                                 (alert_id, key, now, data))
                if cur.rowcount:
                    fresh.append(key)
            # keep the feed bounded
            self._exec("DELETE FROM alert_hits WHERE alert_id=? AND job_key NOT IN (SELECT job_key FROM "
                       "alert_hits WHERE alert_id=? ORDER BY seen DESC LIMIT 500)", (alert_id, alert_id))
        return fresh

    def hits(self, alert_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._exec("SELECT job_key, seen, data FROM alert_hits WHERE alert_id=? ORDER BY seen DESC LIMIT ?",
                          (alert_id, limit))
        return [{"key": r["job_key"], "seen": r["seen"], "match": json.loads(r["data"])} for r in rows]
