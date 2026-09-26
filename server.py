"""ASHA Saathi local server (Python stdlib only - runs on any offline laptop).

    python3 server.py        ->  http://localhost:8000
"""
import json
import os
import queue
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import agent
import dataset
import llm
import store

STATIC = os.path.join(os.path.dirname(__file__), "static")
PORT = int(os.environ.get("PORT", "8000"))


def sync_worker():
    """Flush referrals to the PHC when the device regains connectivity.

    The PHC endpoint is simulated locally (phc_inbox); a 25% random failure
    rate models flaky 2G so the retry/backoff path is visible in the demo.
    """
    while True:
        time.sleep(2)
        if not store.is_online():
            continue
        items = store.q("SELECT * FROM sync_queue WHERE status='pending' ORDER BY priority DESC, created ASC LIMIT 5")
        for it in items:
            backoff = 2 ** it["attempts"]
            if it["attempts"] and time.time() - (it["synced"] or 0) < backoff:
                continue
            if random.random() < 0.25:
                store.q("UPDATE sync_queue SET attempts=attempts+1, last_error=?, synced=? WHERE id=?",
                        ("timeout: weak signal", time.time(), it["id"]))
                continue
            store.ins("INSERT INTO phc_inbox(visit_id,priority,payload,received) VALUES(?,?,?,?)",
                      (it["visit_id"], it["priority"], it["payload"], time.time()))
            store.q("UPDATE sync_queue SET status='synced', synced=?, attempts=attempts+1 WHERE id=?",
                    (time.time(), it["id"]))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/status":
            ok, models = llm.available()
            return self._json({
                "model": llm.MODEL, "model_ready": ok, "online": store.is_online(),
                "queue_pending": store.q("SELECT COUNT(*) n FROM sync_queue WHERE status='pending'", one=True)["n"],
                "queue_synced": store.q("SELECT COUNT(*) n FROM sync_queue WHERE status='synced'", one=True)["n"],
            })
        if p == "/api/patients":
            return self._json(store.q("SELECT * FROM patients ORDER BY id"))
        if p == "/api/queue":
            return self._json(store.q("SELECT id,visit_id,priority,status,attempts,last_error,payload FROM sync_queue ORDER BY id DESC"))
        if p == "/api/phc":
            return self._json(store.q("SELECT * FROM phc_inbox ORDER BY priority DESC, received DESC"))
        if p == "/api/dataset_case":
            # A random real antenatal record from the UCI Maternal Health Risk dataset.
            label = "high risk" if "risk=high" in self.path else random.choice(["high risk", "mid risk", "low risk"])
            r = random.choice([x for x in dataset.load() if x["RiskLevel"] == label])
            c = dataset.to_case(r)
            pid = store.ins("INSERT INTO patients(name,age_months,sex,village,pregnant,created) VALUES(?,?,?,?,?,?)",
                            (f"UCI record #{c['row']}", c["age_years"] * 12, "F", "UCI dataset", 1, time.time()))
            return self._json(dict(c, patient_id=pid))
        if p == "/api/visits":
            return self._json(store.q("SELECT v.id,v.created,v.triage,v.status,v.complaint,p.name FROM visits v JOIN patients p ON p.id=v.patient_id ORDER BY v.id DESC LIMIT 30"))
        # static
        f = "index.html" if p in ("/", "") else p.lstrip("/")
        path = os.path.normpath(os.path.join(STATIC, f))
        if not path.startswith(STATIC) or not os.path.isfile(path):
            return self._json({"error": "not found"}, 404)
        ctype = "text/html; charset=utf-8" if path.endswith(".html") else "application/octet-stream"
        with open(path, "rb") as fh:
            b = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        p = self.path
        body = self._body()
        if p == "/api/network":
            store.set_online(bool(body.get("online")))
            return self._json({"online": store.is_online()})
        if p == "/api/patients":
            pid = store.ins("INSERT INTO patients(name,age_months,sex,village,pregnant,created) VALUES(?,?,?,?,?,?)",
                            (body["name"], int(body.get("age_months") or 0), body.get("sex", ""),
                             body.get("village", ""), 1 if body.get("pregnant") else 0, time.time()))
            return self._json({"id": pid})
        if p == "/api/run":
            return self._stream_run(body)
        self._json({"error": "not found"}, 404)

    def _stream_run(self, body):
        """Run the agent and stream every step as newline-delimited JSON."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = queue.Queue()
        img = body.get("image") or None
        if img and "," in img:
            img = img.split(",", 1)[1]

        def work():
            try:
                agent.run_visit(int(body["patient_id"]), body.get("complaint", ""),
                                body.get("vitals", {}), img, q.put)
            except Exception as e:  # never leave the worker hanging
                q.put({"phase": "ERROR", "kind": "error", "data": {"message": str(e)}})
            q.put(None)

        threading.Thread(target=work, daemon=True).start()
        while True:
            ev = q.get()
            if ev is None:
                break
            try:
                self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
            except BrokenPipeError:
                break


if __name__ == "__main__":
    store.db()
    threading.Thread(target=sync_worker, daemon=True).start()
    threading.Thread(target=llm.warm_up, daemon=True).start()
    print(f"ASHA Saathi running on http://localhost:{PORT}  (model: {llm.MODEL})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
