"""NEER case database (SQLite, file data/neer.db): the permanent record of every case.

Why SQLite: one file, no server to install, ACID transactions, and several processes (the dashboard, the
REST API and the 4 MCP server processes) can read and write it at the same time (WAL mode).

Tables (one row per ...):
    cases        case: scenario, seed, brain, tool mode, status, tier, zone, leak size, verdict, visits ...
    timeline     agent message (who said what, when, which AI provider)
    ledger       evidence-ledger row (dimension, finding, which way it points, reliability, source tool)
    approvals    human decision at a gate (plan / dig): approved?, by whom, with which role
    work_orders  crew work order (acoustic / dig), who approved it, its status and result

Writers: agents/graph.py (after every agent step), tools/field.py (work orders).
Readers: the dashboard "Database & API" tab and the REST API (neer/api/server.py).
The tool-call trace lives in its own SQLite file (data/trace.db, see tools/resilience.py).
A database error is logged and never stops a case: the agents must keep running.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from neer import config
from neer.log import get_logger

log = get_logger("neer.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    scenario    TEXT, seed INTEGER, brain TEXT, tool_mode TEXT,
    status      TEXT, tier TEXT, zone TEXT, leak_lps REAL, verdict TEXT,
    visits      INTEGER DEFAULT 0, replans INTEGER DEFAULT 0, contractor TEXT,
    created_at  TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id), ts TEXT, node TEXT,
    agent TEXT, kind TEXT, provider TEXT, text TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id), sim_when TEXT, dimension TEXT,
    finding TEXT, supports TEXT, reliability TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id), ts TEXT, gate TEXT,
    approved INTEGER, by_name TEXT, role TEXT, area TEXT
);
CREATE TABLE IF NOT EXISTS work_orders (
    case_id TEXT NOT NULL, work_order_id TEXT NOT NULL, area_id TEXT, action TEXT, status TEXT,
    result TEXT, approved_by TEXT, approver_role TEXT, updated_at TEXT,
    PRIMARY KEY (case_id, work_order_id)
);
CREATE INDEX IF NOT EXISTS ix_timeline_case ON timeline(case_id);
CREATE INDEX IF NOT EXISTS ix_ledger_case ON ledger(case_id);
CREATE INDEX IF NOT EXISTS ix_approvals_case ON approvals(case_id);
"""
TABLES = ("cases", "timeline", "ledger", "approvals", "work_orders")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(readonly: bool = False):
    """One short connection per operation: commit on success, roll back on error, always close."""
    path = config.CASE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    else:
        db = sqlite3.connect(path, timeout=5)
        db.execute("PRAGMA journal_mode=WAL")          # readers never block the writer
        db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    try:
        yield db
        if not readonly:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init() -> None:
    with connect():
        pass


# ------------------------------------------------------------------ writers
def open_case(case_id: str, scenario: str, seed: int, brain: str, tool_mode: str) -> None:
    try:
        with connect() as db:
            db.execute("INSERT OR REPLACE INTO cases (case_id, scenario, seed, brain, tool_mode, status, created_at, "
                       "updated_at) VALUES (?,?,?,?,?,?,?,?)",
                       (case_id, scenario, seed, brain, tool_mode, "open", _now(), _now()))
    except sqlite3.Error as e:
        log.warning(f"case database: could not open case {case_id}: {e}")


def record_step(node: str, before: dict, update: dict) -> None:
    """Called after every agent step (graph.py): store its messages, evidence and human decisions,
    and refresh the case row. `before` is the state the node saw, `update` what it returned."""
    case_id = before.get("case_id")
    if not case_id or not isinstance(update, dict):
        return
    s = {**before, **update}
    ts = _now()
    try:
        with connect() as db:
            db.execute("INSERT OR IGNORE INTO cases (case_id, scenario, status, created_at) VALUES (?,?,?,?)",
                       (case_id, s.get("scenario"), "open", ts))
            db.execute("UPDATE cases SET status=?, tier=?, zone=?, leak_lps=?, verdict=?, visits=?, replans=?, "
                       "contractor=?, updated_at=? WHERE case_id=?",
                       (s.get("status"), s.get("tier"), s.get("zone"), s.get("leak_size_lps"), s.get("verdict"),
                        s.get("visits", 0), s.get("replans", 0), s.get("contractor"), ts, case_id))
            for e in update.get("timeline") or []:
                db.execute("INSERT INTO timeline (case_id, ts, node, agent, kind, provider, text) VALUES (?,?,?,?,?,?,?)",
                           (case_id, ts, node, e.get("agent"), e.get("kind"), e.get("provider"), e.get("text")))
            for r in update.get("ledger") or []:
                db.execute("INSERT INTO ledger (case_id, sim_when, dimension, finding, supports, reliability, source) "
                           "VALUES (?,?,?,?,?,?,?)", (case_id, r.get("when"), r.get("dimension"), r.get("finding"),
                                                      r.get("supports"), r.get("reliability"), r.get("source")))
            if node in ("approve_plan", "approve_dig"):
                ok = bool(update.get("plan_approved")) if node == "approve_plan" else update.get("next_action") == "dig"
                who = update.get("approval_by") or update.get("dig_approver")
                role = update.get("approval_role") or update.get("dig_approver_role")
                db.execute("INSERT INTO approvals (case_id, ts, gate, approved, by_name, role, area) VALUES (?,?,?,?,?,?,?)",
                           (case_id, ts, "plan" if node == "approve_plan" else "dig", int(ok), who, role,
                            before.get("current_area")))
    except sqlite3.Error as e:
        log.warning(f"case database: could not record step {node} of {case_id}: {e}")


def save_work_order(wo) -> None:
    """Insert or update one crew work order (called by the field tools, also inside the MCP server process)."""
    try:
        with connect() as db:
            db.execute("INSERT OR REPLACE INTO work_orders (case_id, work_order_id, area_id, action, status, result, "
                       "approved_by, approver_role, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (wo.case_id, wo.work_order_id, wo.area_id, wo.action, wo.status, wo.result, wo.approved_by,
                        wo.approver_role, _now()))
    except sqlite3.Error as e:
        log.warning(f"case database: could not save work order {wo.work_order_id}: {e}")


# ------------------------------------------------------------------ readers
def _rows(sql: str, args: tuple = ()) -> list[dict]:
    if not config.CASE_DB.exists():
        return []
    with connect(readonly=True) as db:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def list_cases(limit: int = 100) -> list[dict]:
    return _rows("SELECT * FROM cases ORDER BY updated_at DESC LIMIT ?", (limit,))


def get_case(case_id: str) -> dict | None:
    rows = _rows("SELECT * FROM cases WHERE case_id=?", (case_id,))
    if not rows:
        return None
    return {**rows[0],
            "timeline": _rows("SELECT ts, node, agent, kind, provider, text FROM timeline WHERE case_id=? ORDER BY id",
                              (case_id,)),
            "ledger": _rows("SELECT sim_when, dimension, finding, supports, reliability, source FROM ledger "
                            "WHERE case_id=? ORDER BY id", (case_id,)),
            "approvals": _rows("SELECT ts, gate, approved, by_name, role, area FROM approvals WHERE case_id=? "
                               "ORDER BY id", (case_id,)),
            "work_orders": _rows("SELECT * FROM work_orders WHERE case_id=? ORDER BY work_order_id", (case_id,))}


def counts() -> dict:
    if not config.CASE_DB.exists():
        return {t: 0 for t in TABLES}
    with connect(readonly=True) as db:
        return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def summary() -> dict:
    """Totals across all stored cases (for the API /kpi endpoint)."""
    r = _rows("SELECT COUNT(*) AS cases, SUM(status='closed') AS closed, SUM(verdict='FIXED') AS fixed, "
              "SUM(status='watch') AS watch, SUM(status='escalated') AS escalated, SUM(visits) AS visits FROM cases")
    out = r[0] if r else {}
    out.update(refused_approvals=(_rows("SELECT COUNT(*) AS n FROM approvals WHERE approved=0") or [{"n": 0}])[0]["n"],
               digs=(_rows("SELECT COUNT(*) AS n FROM work_orders WHERE action IN ('dig','repair')") or [{"n": 0}])[0]["n"])
    return {k: (v or 0) for k, v in out.items()}


def query_readonly(sql: str, limit: int = 200) -> list[dict]:
    """Run ONE read-only SELECT (the dashboard's SQL box). The connection itself is opened read-only,
    so even a sneaky UPDATE/DELETE would be refused by SQLite."""
    q = sql.strip().rstrip(";")
    if not q.lower().startswith(("select", "with")) or ";" in q:
        raise ValueError("only a single SELECT query is allowed")
    return _rows(f"SELECT * FROM ({q}) LIMIT {int(limit)}")
