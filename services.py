"""Connectivity-dependent services: nearest hospitals, geocoding, shareable reports.

These are the ONLY features that touch the internet, and each degrades gracefully:
hospital lists are cached in SQLite so the last known list works offline, and the
report is plain text the worker sends themselves (WhatsApp / SMS deep links).
"""
import json
import math
import time
import urllib.parse
import urllib.request

import store

UA = {"User-Agent": "ASHA-Saathi/1.0 (hackathon prototype)"}
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def _get(url, data=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def geocode(q):
    """Village / town name -> (lat, lon, display name). Cached, so repeat lookups work offline."""
    key = "geo:" + q.strip().lower()
    c = store.q("SELECT v FROM settings WHERE k=?", (key,), one=True)
    if c:
        return json.loads(c["v"])
    if not store.is_online():
        return None
    res = _get(NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "in"}))
    if not res:
        return None
    out = {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]), "name": res[0]["display_name"]}
    store.q("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(out, ensure_ascii=False)))
    return out


GENERIC = {"hospital", "clinic", "eye hospital", "yes", ""}


def _nominatim_hospitals(lat, lon, limit, box=0.12):
    """Fast path (~1 s): Nominatim category search inside a ~13 km box around the point."""
    out = {}
    for term in ("hospital", "clinic"):
        try:
            res = _get(NOMINATIM + "?" + urllib.parse.urlencode({
                "q": term, "format": "jsonv2", "limit": 40, "bounded": 1, "extratags": 1,
                "viewbox": f"{lon - box},{lat + box},{lon + box},{lat - box}"}), timeout=8)
        except Exception:
            continue
        for x in res:
            name = (x.get("name") or "").strip()
            if x.get("category") != "amenity" or name.lower() in GENERIC:
                continue
            la, lo = float(x["lat"]), float(x["lon"])
            tags = x.get("extratags") or {}
            out[name] = {"name": name, "type": x.get("type"), "lat": la, "lon": lo,
                         "distance_km": round(haversine_km(lat, lon, la, lo), 1),
                         "phone": (tags.get("phone") or tags.get("contact:phone") or "").split(";")[0].strip(),
                         "emergency": tags.get("emergency") == "yes",
                         "address": ", ".join((x.get("display_name") or "").split(", ")[1:3]),
                         "maps_url": f"https://www.google.com/maps/dir/?api=1&destination={la},{lo}"}
        if len(out) >= limit * 2:
            break
    hs = sorted(out.values(), key=lambda h: (h["type"] != "hospital", h["distance_km"]))
    return sorted(hs[:limit * 2], key=lambda h: h["distance_km"])[:limit]


def cached_hospitals(lat, lon):
    c = store.q("SELECT v FROM settings WHERE k=?", (f"hosp:{lat:.1f},{lon:.1f}",), one=True)
    return json.loads(c["v"]) if c else None


def prefetch(places):
    """Warm the offline cache for the worker's villages (runs in the background at startup)."""
    for p in places:
        try:
            g = geocode(p)
            if g and not cached_hospitals(g["lat"], g["lon"]):
                nearest_hospitals(g["lat"], g["lon"])
            time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
        except Exception:
            pass


def nearest_hospitals(lat, lon, radius_m=15000, limit=6):
    """Real-time hospital/clinic search via OpenStreetMap, cached for offline use."""
    key = f"hosp:{lat:.1f},{lon:.1f}"  # ~10 km cells
    if not store.is_online():
        cached = store.q("SELECT v FROM settings WHERE k=?", (key,), one=True)
        if cached:
            data = json.loads(cached["v"])
            data.update(cached=True, message="Offline: showing the last saved list. Go online to refresh.")
            return data
        return {"hospitals": [], "cached": False, "message": "Offline and no saved list for this area. Go online once to download it."}
    fast = _nominatim_hospitals(lat, lon, limit)
    if len(fast) >= 3:
        data = {"hospitals": fast, "lat": lat, "lon": lon, "fetched": time.time(), "source": "OpenStreetMap (Nominatim)"}
        store.q("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(data, ensure_ascii=False)))
        data.update(cached=False)
        return data
    ql = (f'[out:json][timeout:10];(node["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});'
          f'way["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon}););out center 60;')
    els, last = None, None
    for url in OVERPASS_MIRRORS:  # public servers are often busy - try mirrors in turn
        try:
            els = _get(url, data=urllib.parse.urlencode({"data": ql}).encode(), timeout=15).get("elements", [])
            break
        except Exception as e:
            last = e
    if els is None:
        cached = store.q("SELECT v FROM settings WHERE k=?", (key,), one=True)
        if cached:
            data = json.loads(cached["v"])
            data.update(cached=True, message="Map servers are busy: showing the last saved list for this area.")
            return data
        raise RuntimeError(f"all map servers busy ({last})")
    out = []
    for e in els:
        t = e.get("tags", {})
        la = e.get("lat") or e.get("center", {}).get("lat")
        lo = e.get("lon") or e.get("center", {}).get("lon")
        if la is None or not t.get("name"):
            continue
        addr = ", ".join(x for x in (t.get("addr:street"), t.get("addr:city") or t.get("addr:district")) if x)
        out.append({
            "name": t.get("name"), "type": t.get("amenity"), "lat": la, "lon": lo,
            "distance_km": round(haversine_km(lat, lon, la, lo), 1),
            "phone": t.get("phone") or t.get("contact:phone") or "",
            "emergency": t.get("emergency") == "yes", "address": addr,
            "maps_url": f"https://www.google.com/maps/dir/?api=1&destination={la},{lo}",
        })
    out.sort(key=lambda h: (h["type"] != "hospital", h["distance_km"]))
    hospitals = sorted(out[:limit * 2], key=lambda h: h["distance_km"])[:limit]
    data = {"hospitals": hospitals, "lat": lat, "lon": lon, "fetched": time.time()}
    store.q("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(data, ensure_ascii=False)))
    data.update(cached=False)
    return data


def visit_report(visit_id):
    """End-to-end plain-text report of one visit, for WhatsApp / SMS / printing."""
    v = store.q("SELECT * FROM visits WHERE id=?", (visit_id,), one=True)
    if not v or not v["result"]:
        return None
    r = json.loads(v["result"])
    p, plan = r["patient"], r["plan"]
    age = f"{p['age_months'] // 12} y" if p["age_months"] >= 24 else f"{p['age_months']} mo"
    label = {"RED": "URGENT REFERRAL (call 108)", "YELLOW": "Visit PHC within 24 hours", "GREEN": "Home care"}[r["triage"]]
    lines = [
        "ASHA Saathi visit report",
        f"Date: {time.strftime('%d %b %Y, %I:%M %p', time.localtime(v['created']))}",
        f"Patient: {p['name']} ({age}{', pregnant' if p['pregnant'] else ''}), {p['village']}",
        f"Problem noted: {v['complaint'][:300]}",
        "",
        f"DECISION: {r['triage']} - {label}",
    ]
    if r.get("handoff"):
        lines.append("Doctor review needed: " + "; ".join(r.get("handoff_reasons", [])))
    lines += ["", "What to do:"] + [f"{i + 1}. {s}" for i, s in enumerate(plan.get("care_plan", []))]
    if plan.get("doses"):
        lines += ["", "Medicines (weight-based):"] + [f"- {d['drug']}: {d['dose']}, {d['frequency']}" for d in plan["doses"]]
    if plan.get("watch_for"):
        lines += ["", "Come back at once if: " + ", ".join(plan["watch_for"])]
    if plan.get("family_message"):
        lines += ["", plan["family_message"]]
    if plan.get("follow_up"):
        lines += ["", "Follow-up: " + plan["follow_up"]]
    lines += ["", "Emergency: 108. Generated on-device by ASHA Saathi (decision support only, not a diagnosis)."]
    return "\n".join(lines)


def stats():
    day = time.time() - 86400
    rows = store.q("SELECT triage, COUNT(*) n FROM visits WHERE status='done' AND created>? GROUP BY triage", (day,))
    by = {r["triage"]: r["n"] for r in rows}
    ms = [json.loads(r["result"]).get("total_ms", 0) for r in
          store.q("SELECT result FROM visits WHERE status='done' AND result IS NOT NULL AND created>? ORDER BY id DESC LIMIT 20", (day,))]
    recent = store.q("SELECT v.id, v.created, v.triage, p.name, p.village FROM visits v JOIN patients p ON p.id=v.patient_id "
                     "WHERE v.status='done' ORDER BY v.id DESC LIMIT 8")
    return {"visits_today": sum(by.values()), "red": by.get("RED", 0), "yellow": by.get("YELLOW", 0), "green": by.get("GREEN", 0),
            "avg_seconds": round(sum(ms) / len(ms) / 1000, 1) if ms else None, "recent": recent}
