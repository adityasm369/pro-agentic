"""SQLite store for Pro Agentic.

One file, WAL, created on first connect. The schema is deliberately small: a
source, an item, a concept, and the many-to-many between item and concept.
Everything the page shows is a query over these four tables, so there is no
second place a count can come from and disagree.
"""
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PA_DB_PATH") or os.path.join(BASE, "data", "store.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS source (
  id         TEXT PRIMARY KEY,        -- slug
  name       TEXT NOT NULL,
  url        TEXT NOT NULL,
  kind       TEXT,                    -- lab | research | newsletter | tooling | community
  enabled    INTEGER NOT NULL DEFAULT 1,
  -- Conditional GET. A feed that has not changed costs one 304 and no parsing,
  -- which is what makes a 15-minute cron polite rather than abusive.
  etag       TEXT,
  modified   TEXT,
  last_ok    REAL,
  last_error TEXT,
  n_items    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item (
  id         TEXT PRIMARY KEY,        -- sha256 of the canonical url
  source_id  TEXT NOT NULL,
  title      TEXT NOT NULL,
  url        TEXT NOT NULL,
  summary    TEXT,
  author     TEXT,
  -- published_at is the feed's own date when it has one. first_seen is ours and
  -- is never null, so an item from a feed with no dates still sorts and still
  -- counts towards a concept's trend.
  published_at REAL,
  first_seen   REAL NOT NULL,
  relevance    INTEGER NOT NULL DEFAULT 0,   -- 0-100, from his profile
  rel_terms    TEXT,                          -- json: which terms matched
  read_at      REAL,
  saved_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_item_when ON item(COALESCE(published_at, first_seen) DESC);
CREATE INDEX IF NOT EXISTS idx_item_source ON item(source_id);

CREATE TABLE IF NOT EXISTS concept (
  slug       TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  aliases    TEXT,                    -- json list, matched whole-word
  kind       TEXT,                    -- protocol | technique | model | tool | idea
  -- An accepted concept is in the library. A candidate was discovered by
  -- emergence and is waiting for him; a rejected one is remembered so it is
  -- not offered again every week.
  status     TEXT NOT NULL DEFAULT 'accepted',   -- accepted | candidate | rejected
  seeded     INTEGER NOT NULL DEFAULT 0,
  first_seen REAL,
  explainer  TEXT,
  explained_at REAL,
  explain_model TEXT,
  explain_items TEXT,                 -- json: the item ids it was grounded in
  notes      TEXT
);

CREATE TABLE IF NOT EXISTS item_concept (
  item_id    TEXT NOT NULL,
  slug       TEXT NOT NULL,
  PRIMARY KEY (item_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_ic_slug ON item_concept(slug);

CREATE TABLE IF NOT EXISTS setting (
  key TEXT PRIMARY KEY, value TEXT, updated_at REAL
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def setting(key, default=None):
    con = connect()
    r = con.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
    con.close()
    return r[0] if r and r[0] is not None else default


def set_setting(key, value):
    import time
    con = connect()
    con.execute("INSERT INTO setting (key,value,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at", (key, value, time.time()))
    con.commit()
    con.close()
