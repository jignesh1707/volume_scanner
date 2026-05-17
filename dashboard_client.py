"""
Dashboard Client
================
Drop-in library every trading bot imports to report its status to a
shared SQLite database. The dashboard_bot reads from this DB.

Design principles:
- Zero dependencies beyond stdlib (sqlite3 is built in).
- Thread-safe; multiple bots write concurrently without coordination.
- Fail-safe: if the DB is locked or unreachable, the bot does NOT crash.
  Reporting failures are silent — your trading bot must never die because
  the dashboard is having a bad day.
- Cheap: one upsert per heartbeat, ~1 KB per bot in the DB.

Usage in your bot:
    from dashboard_client import DashboardClient

    dash = DashboardClient(bot_name="tickrenko")

    # In your main loop, ideally every 15-30 seconds:
    dash.heartbeat(
        status="alive",
        message="Waiting for next brick",
        day_pnl=1240.50,
        day_trades=3,
        open_positions=[
            {"symbol": "NIFTY24OCT24500PE", "qty": -75, "entry": 145.5}
        ],
    )

    # When a trade happens:
    dash.log_trade(
        symbol="NIFTY24OCT24500PE",
        side="SELL", qty=75, price=145.5,
        pnl=0,  # entry trade, no pnl yet
        reason="GREEN_BRICK_RSI_OK",
    )

    # On exceptions:
    dash.log_error("Order rejection: insufficient margin")
"""

import sqlite3
import time
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


DEFAULT_DB_PATH = "/opt/shared/dashboard.db"
SCHEMA_VERSION = 1


SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeats (
    bot_name        TEXT PRIMARY KEY,
    status          TEXT NOT NULL,           -- alive | warning | error | stopped
    message         TEXT,                    -- short freeform status text
    last_seen       REAL NOT NULL,           -- unix ts of last heartbeat
    started_at      REAL,                    -- unix ts of bot startup
    day_pnl         REAL DEFAULT 0,
    day_trades      INTEGER DEFAULT 0,
    open_positions  TEXT,                    -- json list
    errors_last_hour INTEGER DEFAULT 0,
    extra           TEXT                     -- json blob for bot-specific fields
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_name        TEXT NOT NULL,
    ts              REAL NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,           -- BUY | SELL
    qty             INTEGER NOT NULL,
    price           REAL NOT NULL,
    pnl             REAL DEFAULT 0,
    reason          TEXT,
    extra           TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_bot_ts ON trades(bot_name, ts);
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts);

CREATE TABLE IF NOT EXISTS errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_name        TEXT NOT NULL,
    ts              REAL NOT NULL,
    severity        TEXT NOT NULL,           -- info | warning | error | critical
    message         TEXT NOT NULL,
    traceback       TEXT
);
CREATE INDEX IF NOT EXISTS idx_errors_bot_ts ON errors(bot_name, ts);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class DashboardClient:
    """One instance per bot. Safe to keep as a module-level singleton."""

    def __init__(self, bot_name: str, db_path: str = DEFAULT_DB_PATH,
                 timeout: float = 5.0, silent_failures: bool = True):
        self.bot_name = bot_name
        self.db_path = db_path
        self.timeout = timeout
        self.silent_failures = silent_failures
        self._lock = threading.Lock()
        self._started_at = time.time()

        # Ensure parent dir exists
        try:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._fail(f"Cannot create dashboard dir: {e}")
            return

        self._init_db()

    def _conn(self):
        """SQLite connection with WAL mode for concurrent writers."""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout,
                                isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        try:
            with self._lock, self._conn() as c:
                c.executescript(SCHEMA)
                c.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )
        except Exception as e:
            self._fail(f"DB init failed: {e}")

    def _fail(self, msg: str):
        if self.silent_failures:
            return
        raise RuntimeError(f"[DashboardClient/{self.bot_name}] {msg}")

    # -------- heartbeat --------

    def heartbeat(self,
                  status: str = "alive",
                  message: str = "",
                  day_pnl: float = 0.0,
                  day_trades: int = 0,
                  open_positions: Optional[List[Dict[str, Any]]] = None,
                  errors_last_hour: int = 0,
                  extra: Optional[Dict[str, Any]] = None):
        """Call frequently (every 15-30s) from your bot's main loop."""
        try:
            with self._lock, self._conn() as c:
                c.execute("""
                    INSERT INTO heartbeats
                      (bot_name, status, message, last_seen, started_at,
                       day_pnl, day_trades, open_positions, errors_last_hour, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(bot_name) DO UPDATE SET
                      status=excluded.status,
                      message=excluded.message,
                      last_seen=excluded.last_seen,
                      day_pnl=excluded.day_pnl,
                      day_trades=excluded.day_trades,
                      open_positions=excluded.open_positions,
                      errors_last_hour=excluded.errors_last_hour,
                      extra=excluded.extra
                """, (
                    self.bot_name, status, message, time.time(), self._started_at,
                    day_pnl, day_trades,
                    json.dumps(open_positions or []),
                    errors_last_hour,
                    json.dumps(extra or {}),
                ))
        except Exception as e:
            self._fail(f"heartbeat failed: {e}")

    # -------- trades --------

    def log_trade(self, symbol: str, side: str, qty: int, price: float,
                  pnl: float = 0.0, reason: str = "",
                  extra: Optional[Dict[str, Any]] = None):
        try:
            with self._lock, self._conn() as c:
                c.execute("""
                    INSERT INTO trades
                      (bot_name, ts, symbol, side, qty, price, pnl, reason, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.bot_name, time.time(), symbol, side.upper(),
                    int(qty), float(price), float(pnl), reason,
                    json.dumps(extra or {}),
                ))
        except Exception as e:
            self._fail(f"log_trade failed: {e}")

    # -------- errors --------

    def log_error(self, message: str, severity: str = "error",
                   traceback: str = ""):
        try:
            with self._lock, self._conn() as c:
                c.execute("""
                    INSERT INTO errors (bot_name, ts, severity, message, traceback)
                    VALUES (?, ?, ?, ?, ?)
                """, (self.bot_name, time.time(), severity, message, traceback))
        except Exception as e:
            self._fail(f"log_error failed: {e}")

    # -------- bot lifecycle --------

    def mark_stopped(self, reason: str = "shutdown"):
        """Call from a signal handler or finally block."""
        self.heartbeat(status="stopped", message=reason)


# Module-level convenience: many bots prefer a function-style API
_default_client: Optional[DashboardClient] = None


def init(bot_name: str, db_path: str = DEFAULT_DB_PATH):
    global _default_client
    _default_client = DashboardClient(bot_name, db_path)
    return _default_client


def heartbeat(**kwargs):
    if _default_client:
        _default_client.heartbeat(**kwargs)


def log_trade(**kwargs):
    if _default_client:
        _default_client.log_trade(**kwargs)


def log_error(**kwargs):
    if _default_client:
        _default_client.log_error(**kwargs)


if __name__ == "__main__":
    # Self-test
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    print(f"Self-test DB: {tmp.name}")
    c1 = DashboardClient("tickrenko", tmp.name, silent_failures=False)
    c2 = DashboardClient("volumebot", tmp.name, silent_failures=False)

    c1.heartbeat(status="alive", message="warming up",
                  day_pnl=1240.5, day_trades=3,
                  open_positions=[{"symbol": "NIFTY24500PE", "qty": -75, "entry": 145.5}])
    c2.heartbeat(status="alive", message="scanning",
                  extra={"alerts_today": 7})

    c1.log_trade(symbol="NIFTY24500PE", side="SELL", qty=75,
                  price=145.5, reason="GREEN_BRICK_RSI_OK")
    c1.log_error("Test warning", severity="warning")

    # Read back
    with sqlite3.connect(tmp.name) as conn:
        for row in conn.execute("SELECT bot_name, status, day_pnl FROM heartbeats"):
            print(f"  heartbeat: {row}")
        for row in conn.execute("SELECT bot_name, symbol, side, qty, price FROM trades"):
            print(f"  trade: {row}")
        for row in conn.execute("SELECT bot_name, severity, message FROM errors"):
            print(f"  error: {row}")

    os.unlink(tmp.name)
    print("Self-test passed ✓")
