import json
import os
import re
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS writes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id TEXT NOT NULL,
    source_model TEXT NOT NULL,
    ts REAL NOT NULL,
    content TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS units (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    type TEXT NOT NULL,
    text TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    keys TEXT NOT NULL DEFAULT '[]',
    words TEXT NOT NULL DEFAULT '[]',
    attr TEXT NOT NULL DEFAULT '{}',
    source_text TEXT NOT NULL,
    source_model TEXT NOT NULL,
    write_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    superseded_by TEXT,
    superseded_at REAL,
    deleted INTEGER NOT NULL DEFAULT 0,
    embed_model TEXT NOT NULL DEFAULT '',
    embedding TEXT NOT NULL DEFAULT '{}',
    merges INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_units_space ON units(space_id, deleted, superseded_by);
CREATE INDEX IF NOT EXISTS idx_units_fp ON units(space_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_units_space_time ON units(space_id, created_at);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id TEXT NOT NULL,
    source_model TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    response_id TEXT NOT NULL DEFAULT '',
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_usage_space_time ON usage(space_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_model ON usage(space_id, model);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_response
    ON usage(space_id, response_id) WHERE response_id != '';
"""

FTS_SCHEMA = "CREATE VIRTUAL TABLE IF NOT EXISTS units_fts USING fts5(unit_id UNINDEXED, text, keys);"

JSON_FIELDS = ("keys", "words", "attr")


def _row_to_unit(row):
    if row is None:
        return None
    d = dict(row)
    for f in JSON_FIELDS:
        try:
            d[f] = json.loads(d[f])
        except Exception:
            d[f] = [] if f != "attr" else {}
    return d


class Store:
    def __init__(self, db_path):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)
        with self.connection() as con:
            con.executescript(SCHEMA)
            try:
                con.execute(FTS_SCHEMA)
                self.fts_enabled = True
            except sqlite3.OperationalError:
                self.fts_enabled = False
            con.commit()

    def _connect(self):
        con = sqlite3.connect(self.db_path, timeout=20, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=20000")
        return con

    @contextmanager
    def connection(self):
        con = self._connect()
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def write_tx(self):
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def insert_write(self, con, space_id, source_model, ts, content, meta):
        cur = con.execute(
            "INSERT INTO writes(space_id, source_model, ts, content, meta) VALUES (?,?,?,?,?)",
            (space_id, source_model, ts, content, json.dumps(meta or {})),
        )
        return cur.lastrowid

    def get_write(self, write_id):
        with self.connection() as con:
            row = con.execute("SELECT * FROM writes WHERE id=?", (write_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["meta"] = json.loads(d["meta"])
        except Exception:
            d["meta"] = {}
        return d

    def list_active(self, space_id, include_superseded=False, con=None):
        sql = "SELECT * FROM units WHERE space_id=? AND deleted=0"
        if not include_superseded:
            sql += " AND superseded_by IS NULL"
        sql += " ORDER BY created_at ASC"
        if con is not None:
            rows = con.execute(sql, (space_id,)).fetchall()
        else:
            with self.connection() as c:
                rows = c.execute(sql, (space_id,)).fetchall()
        return [_row_to_unit(r) for r in rows]

    def count_superseded(self, space_id):
        with self.connection() as con:
            row = con.execute(
                "SELECT COUNT(*) FROM units WHERE space_id=? AND deleted=0 AND superseded_by IS NOT NULL",
                (space_id,),
            ).fetchone()
        return row[0]

    def get_unit(self, unit_id, include_deleted=False):
        with self.connection() as con:
            row = con.execute("SELECT * FROM units WHERE id=?", (unit_id,)).fetchone()
        u = _row_to_unit(row)
        if u is None or (u["deleted"] and not include_deleted):
            return None
        return u

    def insert_unit(self, con, u):
        con.execute(
            """INSERT INTO units(id, space_id, type, text, fingerprint, keys, words, attr,
               source_text, source_model, write_id, version, created_at, updated_at,
               embed_model, embedding, merges)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                u["id"],
                u["space_id"],
                u["type"],
                u["text"],
                u["fingerprint"],
                json.dumps(u["keys"]),
                json.dumps(u["words"]),
                json.dumps(u["attr"]),
                u["source_text"],
                u["source_model"],
                u["write_id"],
                1,
                u["created_at"],
                u["created_at"],
                u["embed_model"],
                u["embedding"],
                0,
            ),
        )
        if self.fts_enabled:
            con.execute(
                "INSERT INTO units_fts(unit_id, text, keys) VALUES (?,?,?)",
                (u["id"], u["text"], " ".join(u["keys"])),
            )

    def update_unit(self, con, unit_id, u):
        con.execute(
            """UPDATE units SET text=?, fingerprint=?, keys=?, words=?, attr=?, source_text=?,
               source_model=?, version=version+1, updated_at=?, embed_model=?, embedding=?,
               merges=merges+1 WHERE id=?""",
            (
                u["text"],
                u["fingerprint"],
                json.dumps(u["keys"]),
                json.dumps(u["words"]),
                json.dumps(u["attr"]),
                u["source_text"],
                u["source_model"],
                u["updated_at"],
                u["embed_model"],
                u["embedding"],
                unit_id,
            ),
        )
        if self.fts_enabled:
            con.execute("DELETE FROM units_fts WHERE unit_id=?", (unit_id,))
            con.execute(
                "INSERT INTO units_fts(unit_id, text, keys) VALUES (?,?,?)",
                (unit_id, u["text"], " ".join(u["keys"])),
            )

    def bump_merges(self, con, unit_id):
        con.execute("UPDATE units SET merges=merges+1, updated_at=updated_at WHERE id=?", (unit_id,))

    def find_superseded_by(self, unit_id):
        with self.connection() as con:
            rows = con.execute(
                "SELECT * FROM units WHERE superseded_by=? AND deleted=0 ORDER BY created_at ASC",
                (unit_id,),
            ).fetchall()
        return [_row_to_unit(r) for r in rows]

    def supersede(self, con, old_id, new_id, ts):
        con.execute(
            "UPDATE units SET superseded_by=?, superseded_at=? WHERE id=?",
            (new_id, ts, old_id),
        )

    def soft_delete(self, unit_id):
        with self.write_tx() as con:
            row = con.execute("SELECT deleted FROM units WHERE id=?", (unit_id,)).fetchone()
            if row is None or row[0]:
                return False
            con.execute("UPDATE units SET deleted=1, updated_at=updated_at WHERE id=?", (unit_id,))
        return True

    def keyword_scores(self, space_id, query):
        tokens = re.findall(r"[A-Za-z0-9_]+", query or "")
        tokens = [t for t in tokens if len(t) >= 2]
        if not tokens or not self.fts_enabled:
            return {}
        match = " OR ".join(f'"{t}"' for t in tokens)
        sql = """
            SELECT f.unit_id AS uid, bm25(units_fts, 1.0, 3.0) AS s
            FROM units_fts f
            JOIN units u ON u.id = f.unit_id
            WHERE units_fts MATCH ? AND u.space_id=? AND u.deleted=0 AND u.superseded_by IS NULL
        """
        try:
            with self.connection() as con:
                rows = con.execute(sql, (match, space_id)).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {r["uid"]: -r["s"] for r in rows}

    def count_writes(self, space_id):
        with self.connection() as con:
            row = con.execute("SELECT COUNT(*) FROM writes WHERE space_id=?", (space_id,)).fetchone()
        return row[0]

    def insert_usage(self, row):
        with self.write_tx() as con:
            cur = con.execute(
                """INSERT OR IGNORE INTO usage(
                   space_id, source_model, session_id, model, ts, input_tokens,
                   output_tokens, cache_read_tokens, cache_write_tokens,
                   reasoning_tokens, response_id, meta)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["space_id"],
                    row.get("source_model") or "",
                    row.get("session_id") or "",
                    row.get("model") or "",
                    row["ts"],
                    int(row.get("input_tokens") or 0),
                    int(row.get("output_tokens") or 0),
                    int(row.get("cache_read_tokens") or 0),
                    int(row.get("cache_write_tokens") or 0),
                    int(row.get("reasoning_tokens") or 0),
                    row.get("response_id") or "",
                    json.dumps(row.get("meta") or {}),
                ),
            )
            return cur.rowcount > 0

    def usage_summary(self, space_id, since=None, until=None):
        where = ["space_id=?"]
        args = [space_id]
        if since is not None:
            where.append("ts>=?")
            args.append(float(since))
        if until is not None:
            where.append("ts<=?")
            args.append(float(until))
        clause = " AND ".join(where)
        with self.connection() as con:
            total = con.execute(
                f"""SELECT COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens),0) AS input_tokens,
                    COALESCE(SUM(output_tokens),0) AS output_tokens,
                    COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
                    COALESCE(SUM(cache_write_tokens),0) AS cache_write_tokens,
                    COALESCE(SUM(reasoning_tokens),0) AS reasoning_tokens
                    FROM usage WHERE {clause}""",
                args,
            ).fetchone()
            by_model = con.execute(
                f"""SELECT model, COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens),0) AS input_tokens,
                    COALESCE(SUM(output_tokens),0) AS output_tokens,
                    COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
                    COALESCE(SUM(cache_write_tokens),0) AS cache_write_tokens,
                    COALESCE(SUM(reasoning_tokens),0) AS reasoning_tokens
                    FROM usage WHERE {clause}
                    GROUP BY model ORDER BY calls DESC""",
                args,
            ).fetchall()
            by_day = con.execute(
                f"""SELECT date(ts, 'unixepoch') AS day, COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens),0) AS input_tokens,
                    COALESCE(SUM(output_tokens),0) AS output_tokens,
                    COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
                    COALESCE(SUM(reasoning_tokens),0) AS reasoning_tokens
                    FROM usage WHERE {clause}
                    GROUP BY day ORDER BY day DESC LIMIT 31""",
                args,
            ).fetchall()
        totals = dict(total)
        totals["total_tokens"] = (
            totals["input_tokens"]
            + totals["output_tokens"]
            + totals["cache_read_tokens"]
            + totals["cache_write_tokens"]
            + totals["reasoning_tokens"]
        )
        return {
            "space_id": space_id,
            "totals": totals,
            "by_model": [dict(r) for r in by_model],
            "by_day": [dict(r) for r in by_day],
        }
