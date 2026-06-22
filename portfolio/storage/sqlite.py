from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  quantity REAL NOT NULL,
  avg_price REAL NOT NULL,
  currency TEXT NOT NULL,
  target_weight REAL DEFAULT 0,
  strategy_tag TEXT DEFAULT 'Core',
  account_name TEXT DEFAULT 'Manual',
  note TEXT DEFAULT '',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quotes_cache (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  price REAL NOT NULL,
  previous_close REAL NOT NULL,
  currency TEXT NOT NULL,
  provider TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (market, symbol)
);
"""


def init_db(path: str | Path) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
