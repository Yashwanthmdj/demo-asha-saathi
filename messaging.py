"""Automatic background delivery of visit reports by SMS / WhatsApp (Twilio REST API).

Messages go into an on-device outbox first, so a report "sent" with no signal is kept
and delivered by the background worker once connectivity returns (with backoff).

Configure with environment variables before starting the server (never commit keys):
    export TWILIO_ACCOUNT_SID=ACxxxxxxxx
    export TWILIO_AUTH_TOKEN=xxxxxxxx
    export TWILIO_SMS_FROM=+1xxxxxxxxxx            # a Twilio number that can send SMS
    export TWILIO_WHATSAPP_FROM=+14155238886       # Twilio WhatsApp sender (sandbox number by default)
Without them, the app falls back to opening WhatsApp / SMS on the device, pre-filled.
"""
import base64
import json
import os
import time
import urllib.parse
import urllib.request

import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY, visit_id INTEGER, channel TEXT, to_number TEXT, body TEXT,
  status TEXT DEFAULT 'queued', attempts INTEGER DEFAULT 0, last_error TEXT, sid TEXT,
  created REAL, next_try REAL DEFAULT 0, sent REAL);
"""
MAX_ATTEMPTS = 5


def _cfg():
    return {k: os.environ.get(k, "") for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SMS_FROM", "TWILIO_WHATSAPP_FROM")}


def channels():
    c = _cfg()
    base = bool(c["TWILIO_ACCOUNT_SID"] and c["TWILIO_AUTH_TOKEN"])
    return {"sms": base and bool(c["TWILIO_SMS_FROM"]), "whatsapp": base and bool(c["TWILIO_WHATSAPP_FROM"])}


def init():
    store.db().executescript(SCHEMA)


def enqueue(visit_id, phone10, channel, body):
    return store.ins("INSERT INTO outbox(visit_id,channel,to_number,body,created) VALUES(?,?,?,?,?)",
                     (visit_id, channel, "+91" + phone10, body[:1500], time.time()))


def status(msg_id):
    return store.q("SELECT id,channel,to_number,status,attempts,last_error,sent FROM outbox WHERE id=?", (msg_id,), one=True)


def _send(row):
    c = _cfg()
    frm, to = (c["TWILIO_WHATSAPP_FROM"], row["to_number"]) if row["channel"] == "whatsapp" else (c["TWILIO_SMS_FROM"], row["to_number"])
    if row["channel"] == "whatsapp":
        frm, to = "whatsapp:" + frm.replace("whatsapp:", ""), "whatsapp:" + to
    url = f"https://api.twilio.com/2010-04-01/Accounts/{c['TWILIO_ACCOUNT_SID']}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": frm, "Body": row["body"]}).encode()
    auth = base64.b64encode(f"{c['TWILIO_ACCOUNT_SID']}:{c['TWILIO_AUTH_TOKEN']}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={"Authorization": "Basic " + auth})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("sid"), None
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("message", str(e))
        except Exception:
            msg = str(e)
        return None, msg
    except Exception as e:
        return None, str(e)


def flush():
    """Called by the background sync worker whenever the device is online."""
    now = time.time()
    for row in store.q("SELECT * FROM outbox WHERE status='queued' AND next_try<=? ORDER BY id LIMIT 5", (now,)):
        if not channels().get(row["channel"]):
            continue
        sid, err = _send(row)
        if sid:
            store.q("UPDATE outbox SET status='sent', sid=?, sent=?, attempts=attempts+1, last_error=NULL WHERE id=?", (sid, time.time(), row["id"]))
        else:
            attempts = row["attempts"] + 1
            store.q("UPDATE outbox SET attempts=?, last_error=?, next_try=?, status=? WHERE id=?",
                    (attempts, (err or "")[:200], now + 2 ** attempts, "failed" if attempts >= MAX_ATTEMPTS else "queued", row["id"]))
