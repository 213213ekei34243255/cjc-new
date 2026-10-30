"""SQLite store for everything Noah adds: chat log, feedback, unanswered questions, staff-taught
answers, leads / visits / counselling requests, student codes, events and small key-value settings.

It lives next to (not inside) the legacy Postgres chat log, so a broken database can never take the
chatbot down: every public method is safe to call and callers catch StoreError where it matters.
"""

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    sid TEXT,
    role TEXT NOT NULL,
    text TEXT,
    norm TEXT,
    question TEXT,
    reply_id TEXT,
    page TEXT,
    lang TEXT,
    engine TEXT,
    intent TEXT,
    private INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_reply ON messages(reply_id);

CREATE TABLE IF NOT EXISTS feedback (
    reply_id TEXT NOT NULL,
    sid TEXT NOT NULL,
    vote INTEGER NOT NULL,
    comment TEXT,
    ts REAL NOT NULL,
    PRIMARY KEY (reply_id, sid)
);

CREATE TABLE IF NOT EXISTS unanswered (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norm TEXT NOT NULL,
    question TEXT NOT NULL,
    reason TEXT,
    count INTEGER NOT NULL DEFAULT 1,
    first_ts REAL NOT NULL,
    last_ts REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    answer TEXT,
    resolved_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_unanswered_status ON unanswered(status, last_ts);

CREATE TABLE IF NOT EXISTS learned (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    norm TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_ts REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    email TEXT,
    role TEXT,
    board TEXT,
    interest TEXT,
    slot_date TEXT,
    slot_time TEXT,
    pref_time TEXT,
    note TEXT,
    source TEXT,
    consent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    staff_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_kind ON leads(kind, ts);
CREATE INDEX IF NOT EXISTS idx_leads_slot ON leads(slot_date, slot_time);

CREATE TABLE IF NOT EXISTS student_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT NOT NULL UNIQUE,
    hint TEXT,
    label TEXT NOT NULL,
    course TEXT,
    created_ts REAL NOT NULL,
    expires_ts REAL,
    active INTEGER NOT NULL DEFAULT 1,
    uses INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    blurb TEXT,
    starts TEXT,
    ends TEXT,
    location TEXT,
    link_label TEXT,
    link_url TEXT,
    contact TEXT,
    tag TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StoreError(Exception):
    pass


_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return _SPACES.sub(" ", _PUNCT.sub(" ", text)).strip()


def iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=None):
        self.path = path or config.default_db_path()
        self._lock = threading.RLock()
        self._ready = False
        self._init_error = None
        self._ensure()

    # -- plumbing ----------------------------------------------------------------
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure(self):
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            try:
                conn = self._connect()
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.executescript(SCHEMA)
                    conn.commit()
                finally:
                    conn.close()
                self._ready = True
                self._init_error = None
            except sqlite3.Error as exc:
                self._init_error = exc
                raise StoreError(f"database unavailable: {exc}") from exc

    @contextmanager
    def _db(self):
        self._ensure()
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise StoreError(str(exc)) from exc
            finally:
                conn.close()

    @property
    def healthy(self):
        try:
            self._ensure()
            return True
        except StoreError:
            return False

    # -- key/value -----------------------------------------------------------------
    def kv_get(self, key, default=None):
        with self._db() as db:
            row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def kv_set(self, key, value):
        with self._db() as db:
            db.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(value, ensure_ascii=False)))

    def bump_version(self, name="content"):
        """Counter used to invalidate the answer cache when staff change what Noah knows."""
        value = int(self.kv_get("version:" + name, 0)) + 1
        self.kv_set("version:" + name, value)
        return value

    def version(self, name="content"):
        try:
            return int(self.kv_get("version:" + name, 0))
        except (StoreError, ValueError):
            return 0

    # -- chat log ---------------------------------------------------------------------
    def log_message(self, sid, role, text, *, reply_id=None, page=None, lang=None, engine=None,
                    intent=None, question=None, private=False):
        stored = "" if private else (text or "")
        norm = "" if private or role != "user" else normalize(text)[:300]
        with self._db() as db:
            db.execute(
                "INSERT INTO messages(ts,sid,role,text,norm,question,reply_id,page,lang,engine,intent,private)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), sid, role, stored, norm, None if private else question, reply_id,
                 (page or "")[:300], lang, engine, intent, 1 if private else 0))

    def message_for_reply(self, reply_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM messages WHERE reply_id=? AND role='bot'", (reply_id,)).fetchone()
        return dict(row) if row else None

    def add_feedback(self, reply_id, sid, vote, comment=None):
        with self._db() as db:
            db.execute(
                "INSERT INTO feedback(reply_id,sid,vote,comment,ts) VALUES(?,?,?,?,?)"
                " ON CONFLICT(reply_id,sid) DO UPDATE SET vote=excluded.vote, comment=excluded.comment, ts=excluded.ts",
                (reply_id, sid, vote, (comment or "")[:500], time.time()))

    def list_disliked(self, limit=50):
        with self._db() as db:
            rows = db.execute(
                "SELECT f.reply_id, f.comment, f.ts, m.question, m.text AS answer, m.engine, m.page"
                " FROM feedback f LEFT JOIN messages m ON m.reply_id=f.reply_id AND m.role='bot'"
                " WHERE f.vote<0 ORDER BY f.ts DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "ts": iso(r["ts"])} for r in rows]

    # -- unanswered questions ----------------------------------------------------------------
    def record_unanswered(self, question, reason="no_answer"):
        norm = normalize(question)[:300]
        if len(norm) < 3:
            return None
        now = time.time()
        with self._db() as db:
            row = db.execute("SELECT id FROM unanswered WHERE norm=? AND status='open'", (norm,)).fetchone()
            if row:
                db.execute("UPDATE unanswered SET count=count+1, last_ts=? WHERE id=?", (now, row["id"]))
                return row["id"]
            cur = db.execute(
                "INSERT INTO unanswered(norm,question,reason,first_ts,last_ts) VALUES(?,?,?,?,?)",
                (norm, question[:500], reason, now, now))
            return cur.lastrowid

    def list_unanswered(self, status="open", limit=100):
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM unanswered WHERE status=? ORDER BY count DESC, last_ts DESC LIMIT ?",
                (status, limit)).fetchall()
        return [{**dict(r), "first_ts": iso(r["first_ts"]), "last_ts": iso(r["last_ts"]),
                 "resolved_ts": iso(r["resolved_ts"])} for r in rows]

    def answer_unanswered(self, item_id, answer):
        with self._db() as db:
            row = db.execute("SELECT * FROM unanswered WHERE id=?", (item_id,)).fetchone()
            if not row:
                return False
            db.execute("UPDATE unanswered SET status='answered', answer=?, resolved_ts=? WHERE id=?",
                       (answer, time.time(), item_id))
            db.execute("INSERT INTO learned(question,norm,answer,created_ts) VALUES(?,?,?,?)",
                       (row["question"], row["norm"], answer, time.time()))
        self.bump_version()
        return True

    def dismiss_unanswered(self, item_id):
        with self._db() as db:
            cur = db.execute("UPDATE unanswered SET status='dismissed', resolved_ts=? WHERE id=? AND status='open'",
                             (time.time(), item_id))
            return cur.rowcount > 0

    # -- staff-taught answers -----------------------------------------------------------------
    def add_learned(self, question, answer):
        with self._db() as db:
            cur = db.execute("INSERT INTO learned(question,norm,answer,created_ts) VALUES(?,?,?,?)",
                             (question[:500], normalize(question)[:300], answer, time.time()))
            new_id = cur.lastrowid
        self.bump_version()
        return new_id

    def list_learned(self, active_only=True):
        with self._db() as db:
            sql = "SELECT * FROM learned" + (" WHERE active=1" if active_only else "") + " ORDER BY created_ts DESC"
            rows = db.execute(sql).fetchall()
        return [{**dict(r), "created_ts": iso(r["created_ts"])} for r in rows]

    def delete_learned(self, learned_id):
        with self._db() as db:
            cur = db.execute("UPDATE learned SET active=0 WHERE id=?", (learned_id,))
            changed = cur.rowcount > 0
        if changed:
            self.bump_version()
        return changed

    # -- leads / visits / counselling -----------------------------------------------------------
    def add_lead(self, kind, **fields):
        cols = ("name", "phone", "email", "role", "board", "interest", "slot_date", "slot_time",
                "pref_time", "note", "source")
        values = [str(fields.get(c) or "")[:500] for c in cols]
        with self._db() as db:
            cur = db.execute(
                f"INSERT INTO leads(ts,kind,{','.join(cols)},consent) VALUES(?,?,{','.join('?' * len(cols))},?)",
                (time.time(), kind, *values, 1 if fields.get("consent") else 0))
            return cur.lastrowid

    def slot_taken(self, slot_date, slot_time):
        with self._db() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM leads WHERE kind='visit' AND slot_date=? AND slot_time=? AND status!='cancelled'",
                (slot_date, slot_time)).fetchone()
        return row["n"]

    def book_visit(self, capacity, slot_date, slot_time, **fields):
        """Atomic capacity check + insert, so two parents cannot take the last place at once."""
        with self._lock:
            if self.slot_taken(slot_date, slot_time) >= capacity:
                return None
            return self.add_lead("visit", slot_date=slot_date, slot_time=slot_time, **fields)

    def list_leads(self, kind=None, status=None, limit=300):
        sql, args = "SELECT * FROM leads WHERE 1=1", []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        with self._db() as db:
            rows = db.execute(sql, args).fetchall()
        return [{**dict(r), "ts": iso(r["ts"])} for r in rows]

    def update_lead(self, lead_id, status=None, staff_note=None):
        sets, args = [], []
        if status:
            sets.append("status=?")
            args.append(status)
        if staff_note is not None:
            sets.append("staff_note=?")
            args.append(staff_note[:500])
        if not sets:
            return False
        args.append(lead_id)
        with self._db() as db:
            cur = db.execute(f"UPDATE leads SET {','.join(sets)} WHERE id=?", args)
            return cur.rowcount > 0

    # -- student access codes -------------------------------------------------------------------
    @staticmethod
    def _hash_code(code):
        return hashlib.sha256(code.strip().upper().encode()).hexdigest()

    def create_student_code(self, label, course="", days_valid=365):
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        code = f"CJC-{raw[:5]}-{raw[5:]}"
        expires = time.time() + days_valid * 86400 if days_valid else None
        with self._db() as db:
            db.execute("INSERT INTO student_codes(code_hash,hint,label,course,created_ts,expires_ts) VALUES(?,?,?,?,?,?)",
                       (self._hash_code(code), code[-3:], label[:80], course[:40], time.time(), expires))
        return code

    def verify_student_code(self, code):
        if not code or len(code) > 40:
            return None
        with self._db() as db:
            row = db.execute("SELECT * FROM student_codes WHERE code_hash=? AND active=1", (self._hash_code(code),)).fetchone()
            if not row:
                return None
            if row["expires_ts"] and row["expires_ts"] < time.time():
                return None
            db.execute("UPDATE student_codes SET uses=uses+1 WHERE id=?", (row["id"],))
        return dict(row)

    def student_code_active(self, code_id):
        with self._db() as db:
            row = db.execute("SELECT active, expires_ts FROM student_codes WHERE id=?", (code_id,)).fetchone()
        if not row or not row["active"]:
            return False
        return not (row["expires_ts"] and row["expires_ts"] < time.time())

    def list_student_codes(self):
        with self._db() as db:
            rows = db.execute("SELECT id,hint,label,course,created_ts,expires_ts,active,uses FROM student_codes ORDER BY id DESC").fetchall()
        return [{**dict(r), "created_ts": iso(r["created_ts"]), "expires_ts": iso(r["expires_ts"])} for r in rows]

    def revoke_student_code(self, code_id):
        with self._db() as db:
            cur = db.execute("UPDATE student_codes SET active=0 WHERE id=?", (code_id,))
            return cur.rowcount > 0

    # -- events -------------------------------------------------------------------------------------
    def seed_events(self, events):
        with self._db() as db:
            if db.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]:
                return
            for i, e in enumerate(events):
                self._write_event(db, e, i)

    @staticmethod
    def _write_event(db, e, sort=100):
        db.execute(
            "INSERT INTO events(id,title,blurb,starts,ends,location,link_label,link_url,contact,tag,active,sort)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET title=excluded.title, blurb=excluded.blurb, starts=excluded.starts,"
            " ends=excluded.ends, location=excluded.location, link_label=excluded.link_label,"
            " link_url=excluded.link_url, contact=excluded.contact, tag=excluded.tag, active=excluded.active, sort=excluded.sort",
            (e["id"], e["title"], e.get("blurb", ""), e.get("starts") or "", e.get("ends") or "", e.get("location", ""),
             e.get("link_label", ""), e.get("link_url", ""), e.get("contact", ""), e.get("tag", ""),
             1 if e.get("active", True) else 0, int(e.get("sort", sort))))

    def upsert_event(self, e):
        with self._db() as db:
            self._write_event(db, e)
        self.bump_version()

    def delete_event(self, event_id):
        with self._db() as db:
            cur = db.execute("DELETE FROM events WHERE id=?", (event_id,))
            changed = cur.rowcount > 0
        if changed:
            self.bump_version()
        return changed

    def list_events(self, active_only=True):
        with self._db() as db:
            sql = "SELECT * FROM events" + (" WHERE active=1" if active_only else "") + " ORDER BY sort, starts, title"
            rows = db.execute(sql).fetchall()
        return [dict(r) for r in rows]

    # -- analytics ---------------------------------------------------------------------------------------
    def analytics(self, days=30):
        since = time.time() - days * 86400
        out = {"days": days}
        with self._db() as db:
            q = lambda sql, *a: db.execute(sql, a).fetchall()
            out["questions"] = q("SELECT COUNT(*) n FROM messages WHERE role='user' AND ts>=?", since)[0]["n"]
            out["sessions"] = q("SELECT COUNT(DISTINCT sid) n FROM messages WHERE role='user' AND ts>=?", since)[0]["n"]
            out["private_chats"] = q("SELECT COUNT(*) n FROM messages WHERE role='user' AND private=1 AND ts>=?", since)[0]["n"]
            out["per_day"] = [dict(r) for r in q(
                "SELECT date(ts,'unixepoch') d, COUNT(*) n FROM messages WHERE role='user' AND ts>=? GROUP BY d ORDER BY d", since)]
            out["per_hour"] = [dict(r) for r in q(
                "SELECT CAST(strftime('%H',ts,'unixepoch','+5 hours','+30 minutes') AS INTEGER) h, COUNT(*) n"
                " FROM messages WHERE role='user' AND ts>=? GROUP BY h ORDER BY h", since)]
            out["top_questions"] = [dict(r) for r in q(
                "SELECT norm, COUNT(*) n FROM messages WHERE role='user' AND private=0 AND norm!='' AND ts>=?"
                " GROUP BY norm ORDER BY n DESC, MAX(ts) DESC LIMIT 15", since)]
            out["top_pages"] = [dict(r) for r in q(
                "SELECT page, COUNT(*) n FROM messages WHERE role='user' AND page!='' AND ts>=? GROUP BY page ORDER BY n DESC LIMIT 8", since)]
            out["engines"] = [dict(r) for r in q(
                "SELECT engine, COUNT(*) n FROM messages WHERE role='bot' AND ts>=? GROUP BY engine ORDER BY n DESC", since)]
            out["languages"] = [dict(r) for r in q(
                "SELECT lang, COUNT(*) n FROM messages WHERE role='user' AND ts>=? GROUP BY lang ORDER BY n DESC", since)]
            out["intents"] = [dict(r) for r in q(
                "SELECT intent, COUNT(*) n FROM messages WHERE role='bot' AND ts>=? AND intent IS NOT NULL GROUP BY intent ORDER BY n DESC LIMIT 10", since)]
            out["unanswered_open"] = q("SELECT COUNT(*) n FROM unanswered WHERE status='open'")[0]["n"]
            out["thumbs_up"] = q("SELECT COUNT(*) n FROM feedback WHERE vote>0 AND ts>=?", since)[0]["n"]
            out["thumbs_down"] = q("SELECT COUNT(*) n FROM feedback WHERE vote<0 AND ts>=?", since)[0]["n"]
            out["leads"] = [dict(r) for r in q("SELECT kind, COUNT(*) n FROM leads WHERE ts>=? GROUP BY kind", since)]
            out["new_leads"] = q("SELECT COUNT(*) n FROM leads WHERE status='new'")[0]["n"]
        return out

    # -- retention ------------------------------------------------------------------------------------------
    def purge_old(self, days=None):
        days = days or config.CHAT_RETENTION_DAYS
        cutoff = time.time() - days * 86400
        with self._db() as db:
            a = db.execute("DELETE FROM messages WHERE ts<?", (cutoff,)).rowcount
            b = db.execute("DELETE FROM feedback WHERE ts<?", (cutoff,)).rowcount
        return a + b


_store = None
_store_lock = threading.Lock()


def get_store():
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = Store()
    return _store


def reset_store(path=None):
    """Test helper: point the singleton at another database file."""
    global _store
    with _store_lock:
        _store = Store(path)
    return _store
