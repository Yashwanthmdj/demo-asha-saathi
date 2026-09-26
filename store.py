"""Local-first state: SQLite on the device. Nothing leaves until sync."""
import json
import os
import sqlite3
import threading
import time

DB_PATH = os.environ.get("ASHA_DB", os.path.join(os.path.dirname(__file__), "asha.db"))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
  id INTEGER PRIMARY KEY, name TEXT, age_months INTEGER, sex TEXT,
  village TEXT, pregnant INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY, patient_id INTEGER, created REAL, status TEXT,
  complaint TEXT, observations TEXT, triage TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS trace (
  id INTEGER PRIMARY KEY, visit_id INTEGER, ts REAL, phase TEXT, kind TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS sync_queue (
  id INTEGER PRIMARY KEY, visit_id INTEGER, priority INTEGER, payload TEXT,
  status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, last_error TEXT,
  created REAL, synced REAL);
CREATE TABLE IF NOT EXISTS phc_inbox (
  id INTEGER PRIMARY KEY, visit_id INTEGER, priority INTEGER, payload TEXT, received REAL);
CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
"""


def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


_db = None


def db():
    global _db
    if _db is None:
        _db = conn()
        _db.executescript(SCHEMA)
        _seed(_db)
        # Recover visits that were mid-run when the app crashed / battery died.
        _db.execute("UPDATE visits SET status='interrupted' WHERE status='running'")
        _db.commit()
    return _db


def q(sql, args=(), one=False):
    with _lock:
        cur = db().execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        db().commit()
        return (rows[0] if rows else None) if one else rows


def ins(sql, args=()):
    with _lock:
        cur = db().execute(sql, args)
        db().commit()
        return cur.lastrowid


def _seed(c):
    if c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]:
        return
    now = time.time()
    pts = [
        ("Baby Lakshmi", 8, "F", "Kondapur", 0),
        ("Sunita Devi", 288, "F", "Medchal", 1),
        ("Ravi Kumar", 30, "M", "Shamshabad", 0),
        ("Anjali", 1, "F", "Kondapur", 0),
        ("Arjun", 48, "M", "Ghatkesar", 0),
    ]
    for p in pts:
        c.execute("INSERT INTO patients(name,age_months,sex,village,pregnant,created) VALUES(?,?,?,?,?,?)", (*p, now))
    # Prior history so get_patient_history returns something meaningful.
    c.execute(
        "INSERT INTO visits(patient_id,created,status,complaint,observations,triage,result) VALUES(?,?,?,?,?,?,?)",
        (2, now - 86400 * 21, "done", "Routine ANC visit", json.dumps({"bp_systolic": 132, "bp_diastolic": 86}),
         "GREEN", json.dumps({"summary": "ANC visit 2: BP 132/86 borderline, advised recheck in 2 weeks. On IFA tablets."})),
    )
    c.execute(
        "INSERT INTO visits(patient_id,created,status,complaint,observations,triage,result) VALUES(?,?,?,?,?,?,?)",
        (1, now - 86400 * 40, "done", "Diarrhoea", json.dumps({}),
         "YELLOW", json.dumps({"summary": "Diarrhoea with some dehydration, ORS + zinc given. Weight 7.5 kg."})),
    )
    c.execute("INSERT OR REPLACE INTO settings VALUES('online','0')")


def log(visit_id, phase, kind, data):
    ins("INSERT INTO trace(visit_id,ts,phase,kind,data) VALUES(?,?,?,?,?)",
        (visit_id, time.time(), phase, kind, json.dumps(data, ensure_ascii=False)))


def patient_history(pid):
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    visits = q("SELECT created,complaint,triage,result FROM visits WHERE patient_id=? AND status='done' ORDER BY created DESC LIMIT 5", (pid,))
    hist = []
    for v in visits:
        days = int((time.time() - v["created"]) / 86400)
        summ = json.loads(v["result"] or "{}").get("summary", "")
        hist.append(f"{days} days ago: {v['complaint']} -> {v['triage']}. {summ}")
    return {"patient": p, "previous_visits": hist or ["No previous visits"]}


def is_online():
    r = q("SELECT v FROM settings WHERE k='online'", one=True)
    return bool(r and r["v"] == "1")


def set_online(flag):
    q("INSERT OR REPLACE INTO settings VALUES('online',?)", ("1" if flag else "0",))
